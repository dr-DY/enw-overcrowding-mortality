# --------------------------------------------------
# 🧠 Helper: Parse model coefficients
# --------------------------------------------------
parse_coefs <- function(coef_string) {
  parts <- strsplit(coef_string, ", ")[[1]]
  name_val <- strsplit(parts, " = ")
  coefs <- sapply(name_val, function(x) as.numeric(x[2]))
  names(coefs) <- sapply(name_val, function(x) x[1])
  return(coefs)
}

# --------------------------------------------------
# 🔁 Update occupancy-related variables
# --------------------------------------------------
update_occupancy_dependent_vars <- function(df) {
  # Estimate capacity from original data
  capacity <- df$Avg_Population / (df$Avg_Occupancy_Percentage / 100)
  
  # Recalculate occupancy %
  df$Avg_Occupancy_Percentage <- (df$Avg_Population / capacity) * 100
  df$Avg_Occupancy_Proportion <- df$Avg_Occupancy_Percentage / 100
  
  # Recalculate overcrowding flags
  df$Overcrowded_medium <- as.numeric(df$Avg_Occupancy_Percentage > 100 & df$Avg_Occupancy_Percentage <= 120)
  df$Overcrowded_high <- as.numeric(df$Avg_Occupancy_Percentage > 120)
  
  return(df)
}

# --------------------------------------------------
# 🔍 Predict death rate from coefficients
# --------------------------------------------------
predict_death_rate_from_model <- function(prison_row, coefs) {
  linear_pred <- coefs[["(Intercept)"]]
  for (var in names(coefs)) {
    if (var != "(Intercept)" && var %in% names(prison_row)) {
      value <- prison_row[[var]]
      if (is.na(value) || is.infinite(value)) return(NA)
      linear_pred <- linear_pred + coefs[[var]] * value
    }
  }
  linear_pred <- max(min(linear_pred, 50), -50)  # avoid exp overflow
  return(exp(linear_pred))
}

# --------------------------------------------------
# 🔍 Predict deaths by group category
# --------------------------------------------------
predict_deaths_by_category <- function(prisons_df, results_table, category_vars) {
  category_preds <- list()
  problem_count <- 0
  
  for (i in 1:nrow(prisons_df)) {
    prison <- prisons_df[i, ]
    
    for (outcome in results_table$Outcome) {
      coef_string <- results_table$Coefficients[results_table$Outcome == outcome]
      coefs <- parse_coefs(coef_string)
      pred <- predict_death_rate_from_model(prison, coefs)
      if (is.na(pred)) {
        problem_count <- problem_count + 1
        next
      }
      
      group_key <- paste0(sapply(category_vars, function(col) paste0(col, "=", prison[[col]])), collapse = "|")
      if (!group_key %in% names(category_preds)) {
        category_preds[[group_key]] <- list()
      }
      if (!outcome %in% names(category_preds[[group_key]])) {
        category_preds[[group_key]][[outcome]] <- 0
      }
      
      category_preds[[group_key]][[outcome]] <- category_preds[[group_key]][[outcome]] + (pred * 12)
    }
  }
  
  if (problem_count > 0.2 * nrow(prisons_df)) {
    return(NULL)
  }
  
  return(category_preds)
}

# --------------------------------------------------
# 🚀 Bootstrap function (with group estimates + full update logic)
# --------------------------------------------------
robust_bootstrap_by_category <- function(original_df, n_prisons, target_pop,
                                         results_table, binary_vars,
                                         category_vars, n_bootstrap = 500, ci_level = 0.95) {
  bootstrap_results <- list()
  attempt <- 0
  valid_samples <- 0
  max_attempts <- n_bootstrap * 3
  
  while (valid_samples < n_bootstrap && attempt < max_attempts) {
    attempt <- attempt + 1
    tryCatch({
      boot_indices <- sample(1:nrow(original_df), size=n_prisons, replace=TRUE)
      boot_df <- original_df[boot_indices, ]
      
      # Scale population
      scaling_factor <- target_pop / sum(boot_df$Avg_Population)
      boot_df$Avg_Population <- boot_df$Avg_Population * scaling_factor
      
      # Update occupancy variables
      boot_df <- update_occupancy_dependent_vars(boot_df)
      
      # Update interaction terms
      for (var in binary_vars) {
        if (var %in% names(boot_df)) {
          boot_df[[paste0("Avg_Occupancy_Proportion_", var)]] <- 
            boot_df$Avg_Occupancy_Proportion * boot_df[[var]]
        }
      }
      
      pred <- predict_deaths_by_category(boot_df, results_table, category_vars)
      if (is.null(pred)) next
      
      bootstrap_results[[length(bootstrap_results) + 1]] <- pred
      valid_samples <- valid_samples + 1
      
      if (valid_samples %% 50 == 0) {
        cat("✅ Valid samples:", valid_samples, "of", attempt, "attempts\n")
      }
    }, error = function(e) {})
  }
  
  # Aggregate bootstrap results
  agg <- list()
  for (res in bootstrap_results) {
    for (group in names(res)) {
      if (!group %in% names(agg)) agg[[group]] <- list()
      for (outcome in names(res[[group]])) {
        if (!outcome %in% names(agg[[group]])) agg[[group]][[outcome]] <- c()
        agg[[group]][[outcome]] <- c(agg[[group]][[outcome]], res[[group]][[outcome]])
      }
    }
  }
  
  # Summarise
  summary <- data.frame(
    Group = character(), Outcome = character(), Median = numeric(),
    CI_Lower = numeric(), CI_Upper = numeric(), stringsAsFactors = FALSE
  )
  
  alpha <- 1 - ci_level
  for (group in names(agg)) {
    for (outcome in names(agg[[group]])) {
      vals <- agg[[group]][[outcome]]
      summary <- rbind(summary, data.frame(
        Group = group,
        Outcome = outcome,
        Median = median(vals, na.rm = TRUE),
        CI_Lower = quantile(vals, alpha/2, na.rm = TRUE),
        CI_Upper = quantile(vals, 1 - alpha/2, na.rm = TRUE)
      ))
    }
  }
  
  return(summary)
}




# -------------------------------
# 🔢 Setup
# -------------------------------
df <- read.csv("C:/Users/Denis/Desktop/Prison_capacity/Predictive_modelling/prison_agg_data_2014_2024.csv")

category_vars <- c("A", "B", "C", "YOI", "Male", "Female_closed")
binary_vars <- c("A", "B", "C", "D", "YOI", "Male", "Female_open", "Female_closed")

# Replace with your actual results object if it's saved elsewhere
# results <- readRDS("model_results.rds")

# -------------------------------
# 🚀 Run Bootstrap
# -------------------------------
summary_by_group <- robust_bootstrap_by_category(
  original_df = df,
  n_prisons = 132,
  target_pop = 86000,
  results_table = results,
  binary_vars = binary_vars,
  category_vars = category_vars,
  n_bootstrap = 1000
)

# -------------------------------
# 📊 Output
# -------------------------------
print(summary_by_group)
