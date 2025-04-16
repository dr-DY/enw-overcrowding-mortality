library(dplyr)
library(purrr)
library(stringr)
library(ggplot2)
library(viridis)
library(openxlsx)


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
  
  capacity <- df$Avg_Population / (df$Avg_Occupancy_Percentage / 100)
  
  
  df$Avg_Occupancy_Percentage <- (df$Avg_Population_Scaled / capacity) * 100
  df$Avg_Occupancy_Proportion <- df$Avg_Occupancy_Percentage / 100
  df$Avg_Op_Capacity_by_InUseCNA <- round(df$Avg_Population_Scaled / df$Avg_Occupancy_Proportion)
  
  df$Well_below_capacity   <- as.numeric(df$Avg_Occupancy_Percentage < 90)
  df$Close_to_capacity     <- as.numeric(df$Avg_Occupancy_Percentage > 90 & df$Avg_Occupancy_Percentage <= 100)
  df$Overcrowded_light     <- as.numeric(df$Avg_Occupancy_Percentage > 100 & df$Avg_Occupancy_Percentage <= 110)
  df$Overcrowded_medium    <- as.numeric(df$Avg_Occupancy_Percentage > 110 & df$Avg_Occupancy_Percentage <= 120)
  df$Overcrowded_high      <- as.numeric(df$Avg_Occupancy_Percentage > 120)
  
  df$Avg_Population <- df$Avg_Population_Scaled
  
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
  linear_pred <- max(min(linear_pred, 50), -50)
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
      
      # this bit double the functionality of the pre-boorstrp processing
      # can be used, it it needs to be dome ehre for some reason
      # # Scale population
      # scaling_factor <- target_pop / sum(boot_df$Avg_Population)
      # boot_df$Avg_Population_Scaled <- boot_df$Avg_Population * scaling_factor
      # 
      # boot_df <- update_occupancy_dependent_vars(boot_df)
      #  
      #  for (var in binary_vars) {
      #    if (var %in% names(boot_df)) {
      #      boot_df[[paste0("Avg_Occupancy_Proportion_", var)]] <- 
      #        boot_df$Avg_Occupancy_Proportion * boot_df[[var]]
      #    }
      #  }
      
      pred <- predict_deaths_by_category(boot_df, results_table, category_vars)
      if (is.null(pred)) next
      
      bootstrap_results[[length(bootstrap_results) + 1]] <- pred
      valid_samples <- valid_samples + 1
      
      if (valid_samples %% 50 == 0) {
        cat("✅ Valid samples:", valid_samples, "of", attempt, "attempts\n")
      }
    }, error = function(e) {})
  }
  
  # Aggregate
  agg <- list()
  total_draws <- list()  # To collect total outcome values across categories
  
  for (res in bootstrap_results) {
    total_outcomes <- list()
    
    for (group in names(res)) {
      if (!group %in% names(agg)) agg[[group]] <- list()
      
      for (outcome in names(res[[group]])) {
        if (!outcome %in% names(agg[[group]])) agg[[group]][[outcome]] <- c()
        agg[[group]][[outcome]] <- c(agg[[group]][[outcome]], res[[group]][[outcome]])
        
        if (!outcome %in% names(total_outcomes)) total_outcomes[[outcome]] <- 0
        total_outcomes[[outcome]] <- total_outcomes[[outcome]] + res[[group]][[outcome]]
      }
    }
    
    for (outcome in names(total_outcomes)) {
      if (!outcome %in% names(total_draws)) total_draws[[outcome]] <- c()
      total_draws[[outcome]] <- c(total_draws[[outcome]], total_outcomes[[outcome]])
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
  
  # Append TOTAL group with quantile-based CIs
  for (outcome in names(total_draws)) {
    vals <- total_draws[[outcome]]
    summary <- rbind(summary, data.frame(
      Group = "TOTAL",
      Outcome = outcome,
      Median = median(vals, na.rm = TRUE),
      CI_Lower = quantile(vals, alpha/2, na.rm = TRUE),
      CI_Upper = quantile(vals, 1 - alpha/2, na.rm = TRUE)
    ))
  }
  
  attr(summary, "total_draws") <- total_draws
  return(summary)
}



# # -------------------------------
# # 🚀 Run Bootstrap
# # -------------------------------
# summary_by_group <- robust_bootstrap_by_category(
#   original_df = df,
#   n_prisons = N_prisons,
#   target_pop = Population_projected,
#   results_table = results,
#   binary_vars = binary_vars,
#   category_vars = category_vars,
#   n_bootstrap = 1000
# )
# 
# # -------------------------------
# # 📊 Output
# # -------------------------------
# print(summary_by_group)





# --------------------------------------------------
# 📊 Prison Mortality Data Formatter (Minimal Version)
# --------------------------------------------------
format_bootstrap_results <- function(summary_by_group, scaling_factor) {
  if (!all(c("Group", "Outcome", "Median", "CI_Lower", "CI_Upper") %in% names(summary_by_group))) {
    stop("Input data frame must contain Group, Outcome, Median, CI_Lower, and CI_Upper columns")
  }
  
  total_draws <- attr(summary_by_group, "total_draws")
  
  summary_by_group$PrisonType <- ifelse(summary_by_group$Group == "TOTAL", "TOTAL",
                                        sapply(summary_by_group$Group, function(group) {
                                          is_A <- grepl("A=1", group)
                                          is_B <- grepl("B=1", group)
                                          is_C <- grepl("C=1", group)
                                          is_D <- grepl("D=1", group)
                                          is_YOI <- grepl("YOI=1", group)
                                          is_Male <- grepl("Male=1", group)
                                          is_Female_closed <- grepl("Female_closed=1", group)
                                          is_Female_open <- grepl("Female_open=1", group)
                                          
                                          if (is_B && is_YOI) {
                                            return("B+YOI")
                                          } else if (is_B && is_Female_closed) {
                                            return("Mixed [B + Female (Closed)]")
                                          } else if (is_C && is_YOI) {
                                            return("C+YOI")
                                          } else if (is_YOI && is_Female_closed) {
                                            return("Female (Closed) + YOI")
                                          } else if (is_A) {
                                            return("A")
                                          } else if (is_B) {
                                            return("B")
                                          } else if (is_C) {
                                            return("C")
                                          } else if (is_D) {
                                            return("D")
                                          } else if (is_YOI) {
                                            return("YOI")
                                          } else if (is_Female_closed) {
                                            return("Female (Closed)")
                                          } else if (is_Female_open) {
                                            return("Female (Open)")
                                          } else {
                                            return("Unclassified")
                                          }
                                          
                                        })
  )
  
  cat('Sanity check for prison grouping: ')
  print(table(summary_by_group$PrisonType))
  print(table(summary_by_group$PrisonType, summary_by_group$Outcome))
  
  summary_by_group$Value <- sprintf("%d (%d-%d)", 
                                    round(summary_by_group$Median),
                                    round(summary_by_group$CI_Lower),
                                    round(summary_by_group$CI_Upper))
  
  population_sizes <- c(
    "A" = 4901 * scaling_factor,
    "B" = 26242 * scaling_factor,
    "B+YOI" = 7531 * scaling_factor,
    "Mixed [B + Female (Closed)]" = 1237 * scaling_factor,
    "C" = 32476 * scaling_factor,
    "C+YOI" = 3708 * scaling_factor,
    "YOI" = 2988 * scaling_factor,
    "Female (Closed) + YOI" = 352 * scaling_factor,
    "Female (Closed)" = 2750 * scaling_factor,
    "Female (Open)" = 192 * scaling_factor,
    "D" = 4360 * scaling_factor
  )
  
  summary_by_group$CleanOutcome <- gsub("^Avg_", "", summary_by_group$Outcome)
  summary_by_group$CleanOutcome <- gsub("^Adjusted_", "", summary_by_group$Outcome)
  
  outcome_types <- unique(summary_by_group$CleanOutcome)
  prison_types <- unique(summary_by_group$PrisonType)
  base_types <- setdiff(prison_types, "TOTAL")
  
  result_table <- data.frame(
    PrisonType = base_types,
    Population = sapply(base_types, function(pt) if (pt %in% names(population_sizes)) population_sizes[pt] else NA),
    stringsAsFactors = FALSE
  )
  
  for (outcome in outcome_types) {
    result_table[[outcome]] <- sapply(base_types, function(pt) {
      row_idx <- which(summary_by_group$PrisonType == pt & summary_by_group$CleanOutcome == outcome)
      if (length(row_idx) > 0) summary_by_group$Value[row_idx[1]] else "NA"
    })
  }
  
  total_population <- sum(result_table$Population, na.rm = TRUE)
  result_table$PopulationPercent <- sprintf("%.1f%%", (result_table$Population / total_population) * 100)
  
  col_order <- c("PrisonType", "Population", "PopulationPercent", outcome_types)
  col_order <- col_order[col_order %in% names(result_table)]
  result_table <- result_table[, col_order]
  result_table <- result_table[order(result_table$Population, decreasing = TRUE), ]
  rownames(result_table) <- NULL
  
  totals_row <- data.frame(
    PrisonType = "TOTAL",
    Population = total_population,
    PopulationPercent = "100.0%",
    stringsAsFactors = FALSE
  )
  
  for (outcome in outcome_types) {
    row_idx <- which(summary_by_group$PrisonType == "TOTAL" & summary_by_group$CleanOutcome == outcome)
    if (length(row_idx) > 0) {
      val_str <- summary_by_group$Value[row_idx[1]]
      totals_row[[outcome]] <- val_str
    } else {
      totals_row[[outcome]] <- "NA"
    }
  }
  
  result_table <- rbind(result_table, totals_row)
  return(result_table)
}


# # Example usage:
# formatted <- format_bootstrap_results(summary_by_group, Scaling_factor)
# write.xlsx(formatted,
#            paste0("Output/Predictions/prison_mortality_projections_",
#                   Population_projected,".xlsx"), rowNames = FALSE)
# -------------------------------




# --------------------------------------------------
# 📊 Calculated the predicted number of deaths for projected population sizes
# --------------------------------------------------

# -------------------------------
# 🔢 Setup
# -------------------------------
path_to_agg_data <- "Output/For_analysis/prison_agg_2014_2024_weighted_linear_covid.xlsx"

# Create interaction terms
binary_vars <- c("A", "B", "C", "D", "YOI", "Male", "Female_open", "Female_closed")
category_vars <- c("A", "B", "C", "D", "YOI", "Male", "Female_open", "Female_closed")

# Setting up number of prison to sample (or expected number of prisons)
N_prisons <- 123

# Setting up the size of the population used for weighting (default is 86737)
Baseline_population_size <- 86737

# Create dependent variables for prediction (adjusted monthly 1 to annual 12)
adjustment_factor <- 1

# Your projected population values by year
year_population <- data.frame(
  Year = 2024:2029,
  Population_projected = c(87129, 89100, 93500, 97300, 99800, 100800)
)

# # Your projected population values by year
# year_population <- data.frame(
#   Year = 2028,
#   Population_projected = c(99800)
# )


# Output folder path
output_folder <- "Output/Predictions"

# Loop over years
for (i in 1:nrow(year_population)) {
  
  df <- read.xlsx(path_to_agg_data)

  df$Adjusted_Deaths             <- df$Avg_Deaths * adjustment_factor
  df$Adjusted_Homicide           <- df$Avg_Homicide * adjustment_factor
  df$Adjusted_SelfInflicted      <- df$Avg_SelfInflicted * adjustment_factor
  df$Adjusted_Natural            <- df$Avg_Natural * adjustment_factor
  df$Adjusted_Other              <- df$Avg_Other * adjustment_factor
  df$Adjusted_Other_inclHomicide <- df$Adjusted_Other + df$Adjusted_Homicide
  
  year <- year_population$Year[i]
  target_pop <- year_population$Population_projected[i]
  
  # Calculating scaling factor for formatting
  scaling_factor <- target_pop / Baseline_population_size
  
  # Update scaled population
  df$Avg_Population_Scaled <- df$Avg_Population * scaling_factor
  df <- update_occupancy_dependent_vars(df)


  # Add interaction terms
  for (var in binary_vars) {
    if (var %in% names(df)) {
        df[[paste0("Avg_Occupancy_Proportion_", var)]] <-
        df$Avg_Occupancy_Proportion * df[[var]]
     }
  }
  
  # Run the bootstrap for this year's projected population
  summary_by_group <- robust_bootstrap_by_category(
    original_df = df,
    n_prisons = N_prisons,
    target_pop = target_pop,
    results_table = results,
    binary_vars = binary_vars,
    category_vars = category_vars,
    n_bootstrap = 1000
  )
  

  
  # Format and save
  formatted <- format_bootstrap_results(summary_by_group, scaling_factor)
  output_path <- file.path(output_folder, paste0("prison_mortality_projections_", year, ".xlsx"))
  write.xlsx(formatted, output_path, rowNames = FALSE)
  cat("✅ Saved file for year:", year, "→", output_path, "\n")
}
