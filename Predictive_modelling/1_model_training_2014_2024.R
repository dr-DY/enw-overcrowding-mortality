# ------------------------------
# 1. Load Required Packages
# ------------------------------
if (!require(mpath)) install.packages("mpath")
library(mpath)

if (!require(ggplot2)) install.packages("ggplot2")
library(ggplot2)

if (!require(Metrics)) install.packages("Metrics")
library(Metrics)

if (!require(jsonlite)) install.packages("jsonlite")
library(jsonlite)

library(effects)
library(MASS)

library(dplyr)
library(openxlsx)
library(caret)

# ------------------------------
# 2. Load Data
# ------------------------------
cat("📂 Reading input data...\n")
df <- read.xlsx("Output/For_analysis/prison_agg_2014_2024_weighted_linear_covid.xlsx")
cat("✅ Data loaded. Rows:", nrow(df), "Cols:", ncol(df), "\n")



cat("📦 Applying variable transformations...\n")

# Convert average monthly outcomes to annual or whenever is needed
adjustment_factor              <- 1 # 1 for now adjustment, 12 for annual numbers
df$Adjusted_Deaths             <- df$Avg_Deaths * adjustment_factor
df$Adjusted_Homicide           <- df$Avg_Homicide * adjustment_factor
df$Adjusted_SelfInflicted      <- df$Avg_SelfInflicted * adjustment_factor
df$Adjusted_Natural            <- df$Avg_Natural * adjustment_factor
df$Adjusted_Other              <- df$Avg_Other * adjustment_factor
df$Adjusted_Other_inclHomicide <- df$Adjusted_Other + df$Adjusted_Homicide 



# Create the Avg_Occupancy_Proportion variable
df$Avg_Occupancy_Proportion <- df$Avg_Occupancy_Percentage/100

# Average operational capacity by CNA
df$Avg_Op_Capacity_by_InUseCNA <- round(df$Avg_Population/df$Avg_Occupancy_Proportion)


# Create the overcrowding category variables
df$Well_below_capacity <- as.numeric(df$Avg_Occupancy_Percentage < 90)
df$Close_to_capacity <- as.numeric(df$Avg_Occupancy_Percentage > 90 & df$Avg_Occupancy_Percentage <= 100)
df$Overcrowded_light <- as.numeric(df$Avg_Occupancy_Percentage > 100 & df$Avg_Occupancy_Percentage <= 110)
df$Overcrowded_medium <- as.numeric(df$Avg_Occupancy_Percentage > 110 & df$Avg_Occupancy_Percentage <= 120)
df$Overcrowded_high <- as.numeric(df$Avg_Occupancy_Percentage > 120)


# selecting for future predictions:
df_for_predictions <- df %>%
            dplyr::select(
              Prison_name,
              Avg_Population,
              Avg_Occupancy_Percentage,
              Avg_Occupancy_Proportion,
              Avg_Op_Capacity_by_InUseCNA,
              A, B, C, D,
              YOI,
              Male, Female, Mixed,
              Female_open, Female_closed,
              Highest_category_male,
              Highest_category_female,
              Well_below_capacity,
              Close_to_capacity,
              Overcrowded_light,
              Overcrowded_medium,
              Overcrowded_high
              
            )



# Check the results
table(df$Overcrowded_medium, df$Overcrowded_high, useNA = "ifany")

# ------------------------------
# 3. Feature Engineering
# ------------------------------
# Define all covariates (include the overcrowding variables)
all_covariates <- c("A", "B", "C", "D", "YOI", "Male", "Female_closed", "Female_open", "Avg_Population", 
                    "Well_below_capacity", "Close_to_capacity",
                    "Overcrowded_light", "Overcrowded_medium", "Overcrowded_high")

# Define variables to include in interaction terms
interaction_vars <- c("A", "B", "C", "D", "YOI", "Male", "Female_open", "Female_closed")

# Create interaction terms only for selected variables
cat("🛠️  Feature engineering...\n")
main_interaction_term <- 'Avg_Occupancy_Proportion'

# Check which interactions have sufficient data
valid_interactions <- c()
for (var in interaction_vars) {
  if (sum(df[[main_interaction_term]] != 0 & df[[var]] >= 1) > 2) {  # At least N cases of both being >=1
    valid_interactions <- c(valid_interactions, var)
    cat("Creating interaction for:", var, "\n")
  } else {
    cat("Skipping interaction for:", var, " (insufficient data)\n")
  }
}

# Create interaction terms only for valid interactions
for (var in valid_interactions) {
  df[[paste0(main_interaction_term, '_', var)]] <- df[[main_interaction_term]] * df[[var]]
}

# Define the full set of features for later use
features <- c(
  all_covariates,
  paste0(main_interaction_term, '_', valid_interactions)
)

cat("✅ Features constructed:", length(features), "variables\n")
cat("✅ Main covariates:", length(all_covariates), "variables\n")
cat("✅ Valid interaction terms:", length(valid_interactions), "variables\n")

# Quick check of the interaction variables that were created
if(length(valid_interactions) > 0) {
  cat("First few rows of interaction variables:\n")
  print(head(df[, grep(paste0(main_interaction_term, '_'), names(df))]))
} else {
  cat("No valid interaction terms were created\n")
}

# ------------------------------
# 4. Initialize Results DataFrame
# ------------------------------
results <- data.frame(
  Outcome = character(),
  Formula = character(),
  Lambda = numeric(),
  AIC = numeric(),
  RMSE = numeric(),
  Pseudo_R2 = numeric(),
  NonZero_Coefficients = integer(),
  Selected_Variables = character(),
  Coefficients = character(),
  Model_Type = character(),
  stringsAsFactors = FALSE
)

# ------------------------------
# 5. Function to Fit and Save Model Results with Error Handling
# ------------------------------
fit_nb_model <- function(outcome_var) {
  cat("\n===============================\n")
  cat("🔍 Modeling:", outcome_var, "\n")
  cat("===============================\n\n")
  
  df_model <- df[, c(outcome_var, features)]
  df_model <- na.omit(df_model)
  names(df_model)[1] <- "y"
  
  cat("✅ Observations after NA removal:", nrow(df_model), "\n")
  if (nrow(df_model) == 0) {
    stop(paste("❌ No data left for outcome", outcome_var, "after na.omit()"))
  }
  
  # Check for zero counts
  zero_count <- sum(df_model$y == 0)
  cat("📊 Zero values in outcome:", zero_count, "out of", nrow(df_model), "\n")
  
  # if weighted dataset is used, the weights are not needed
  #weights_vec <- as.numeric(df_model$Avg_Population)
  
  # Try with tryCatch to handle errors
  tryCatch({
    set.seed(42)
    cat("🚦 Running cv.glmregNB with robust settings...\n")
    
    cvfit <- cv.glmregNB(
      formula = y ~ .,
      data = df_model,
      penalty = "enet",
      #alpha = 0.9,
      #alpha = 1, # makes it effectively lasso
      alpha = 0.5, # makes it enet
      nfolds = 10,
      standardize = TRUE,
      tol = 1e-4,
      maxit = 1000
    )
    
    lambda_opt <- cvfit$lambda.optim
    cat("📌 Lambda selected (lambda.optim):", lambda_opt, "\n")
    
    # ✔️ Only print a few values from lambda path for context
    cat("📊 First few lambdas in sequence: ", paste(head(cvfit$lambda, 5), collapse = ", "), "...\n")
    
    # Proceed with refit
    X <- as.matrix(df_model[, features])
    model_data <- data.frame(y = df_model$y, X)
    
    cat("🔁 Refitting model using lambda.optim...\n")
    fit_nb <- glmregNB(
      formula = y ~ .,
      data = model_data,
      penalty = "enet",
      #alpha = 1, # makes it effectively lasso
      alpha = 0.5, # makes it an elastic net
      lambda = lambda_opt,
      standardize = TRUE,
      tol = 1e-4,
      maxit = 1000
    )
    
    
    cat("📈 Predicting on full data...\n")
    predicted <- as.vector(predict(fit_nb, newx = as.data.frame(X), type = "response"))
    
    residuals <- df_model$y - predicted
    rss <- sum(residuals^2)
    tss <- sum((df_model$y - mean(df_model$y))^2)
    pseudo_r2 <- 1 - rss / tss
    rmse_val <- rmse(df_model$y, predicted)
    
    lambda_index <- which.min(abs(fit_nb$lambda - lambda_opt))
    cat("🔎 lambda_index used for coef/AIC extraction:", lambda_index, "\n")
    cat("📐 Model lambda path:\n")
    print(fit_nb$lambda)
    cat("📐 Model AIC path:\n")
    print(fit_nb$aic)
    
    best_aic <- fit_nb$aic[lambda_index]
    
    cat("🔍 Extracting coefficients at selected lambda...\n")
    coefs_at_lambda <- coef(fit_nb)
    
    if (!is.numeric(coefs_at_lambda)) {
      stop("❌ Unexpected format: coefficients are not numeric.")
    }
    
    selected_vars <- names(coefs_at_lambda[which(coefs_at_lambda != 0)])
    n_nonzero <- length(setdiff(selected_vars, "(Intercept)"))
    selected_var_string <- paste(setdiff(selected_vars, "(Intercept)"), collapse = ", ")
    formula_str <- paste("y ~", paste(features, collapse = " + "))
    
    # Save coefficients as readable formula-style string
    coef_formula_text <- paste(names(coefs_at_lambda), round(coefs_at_lambda, 6), sep = " = ", collapse = ", ")
    
    cat("📝 Creating results row...\n")
    results_row <- data.frame(
      Outcome = outcome_var,
      Formula = formula_str,
      Lambda = lambda_opt,
      AIC = best_aic,
      RMSE = rmse_val,
      Pseudo_R2 = pseudo_r2,
      NonZero_Coefficients = n_nonzero,
      Selected_Variables = selected_var_string,
      Coefficients = coef_formula_text,
      Model_Type = "Negative Binomial",
      stringsAsFactors = FALSE
    )
    
    cat("📊 Appending to results...\n")
    assign("results", rbind(get("results", envir = .GlobalEnv), results_row), envir = .GlobalEnv)
    
    cat("📷 Plotting predictions...\n")
    p <- ggplot(data.frame(observed = df_model$y, predicted = predicted),
                aes(x = predicted, y = observed)) +
      geom_point(alpha = 0.7, color = "#1f77b4") +
      geom_abline(intercept = 0, slope = 1, linetype = "dashed", color = "gray40") +
      labs(
        title = paste("Predicted vs Observed for", outcome_var),
        x = "Predicted",
        y = "Observed"
      ) +
      theme_minimal(base_size = 14)
    print(p)
    
  }, error = function(e) {
    cat("❌ Error in negative binomial model:", conditionMessage(e), "\n")
    cat("⚠️ Switching to Poisson model...\n")
    
    # Try Poisson GLM directly since it's more stable
    tryCatch({
      # Create formula
      glm_formula <- as.formula(paste("y ~", paste(features, collapse = " + ")))
      
      # Fit model
      simple_model <- glm(
        formula = glm_formula,
        data = df_model,
        family = poisson(link = "log"),
        #weights = weights_vec
      )
      
      # Get predictions
      predicted <- predict(simple_model, type = "response")
      
      # Calculate metrics
      residuals <- df_model$y - predicted
      rss <- sum(residuals^2)
      tss <- sum((df_model$y - mean(df_model$y))^2)
      pseudo_r2 <- 1 - rss / tss
      rmse_val <- rmse(df_model$y, predicted)
      
      # Extract coefficients
      coefs <- coef(simple_model)
      nonzero_coefs <- coefs[which(abs(coefs) > 1e-5)]
      selected_vars <- names(nonzero_coefs)
      n_nonzero <- length(setdiff(selected_vars, "(Intercept)"))
      selected_var_string <- paste(setdiff(selected_vars, "(Intercept)"), collapse = ", ")
      formula_str <- paste("y ~", paste(features, collapse = " + "))
      
      # Save coefficients
      coef_formula_text <- paste(names(nonzero_coefs), round(nonzero_coefs, 6), 
                                 sep = " = ", collapse = ", ")
      
      # Create results row
      results_row <- data.frame(
        Outcome = outcome_var,
        Formula = formula_str,
        Lambda = NA,  # Not applicable for glm
        AIC = AIC(simple_model),
        RMSE = rmse_val,
        Pseudo_R2 = pseudo_r2,
        NonZero_Coefficients = n_nonzero,
        Selected_Variables = selected_var_string,
        Coefficients = coef_formula_text,
        Model_Type = "Standard Poisson GLM",
        stringsAsFactors = FALSE
      )
      
      cat("📊 Appending to results...\n")
      assign("results", rbind(get("results", envir = .GlobalEnv), results_row), envir = .GlobalEnv)
      
      cat("📷 Plotting predictions...\n")
      p <- ggplot(data.frame(observed = df_model$y, predicted = predicted),
                  aes(x = predicted, y = observed)) +
        geom_point(alpha = 0.7, color = "#1f77b4") +
        geom_abline(intercept = 0, slope = 1, linetype = "dashed", color = "gray40") +
        labs(
          title = paste("Predicted vs Observed for", outcome_var, "(Poisson)"),
          x = "Predicted",
          y = "Observed"
        ) +
        theme_minimal(base_size = 14)
      print(p)
      
    }, error = function(e2) {
      cat("❌ Even standard Poisson model failed:", conditionMessage(e2), "\n")
    })
  })
  
  cat("✅ Done with", outcome_var, "\n")
}


# ------------------------------
# 6. Run for Each Outcome
# ------------------------------
cat("🚀 Running models for all outcomes...\n")
#outcomes <- c("Avg_Deaths", "Avg_Homicide", "Avg_SelfInflicted", "Avg_Natural", "Avg_Other")
outcomes <- c("Adjusted_Deaths", "Adjusted_Homicide", "Adjusted_SelfInflicted", "Adjusted_Natural",
              "Adjusted_Other", "Adjusted_Other_inclHomicide")
model_outputs <- lapply(outcomes, fit_nb_model)

# ------------------------------
# 7. Review Results Table
# ------------------------------
cat("\n=== ✅ Final Results Table ===\n")
print(results)




# Function to create a formatted summary and visualizations of model results
# Function to create a formatted summary and visualizations of model results
# Function to create a formatted summary and visualizations of model results
format_model_results <- function(results) {
  library(ggplot2)
  library(dplyr)
  library(viridis)  # For colorblind-friendly palette
  
  # Create the output directory if it doesn't exist
  output_dir <- "Output/Models_output"
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  # Create a text file for the summary
  summary_file <- file.path(output_dir, "model_summary.txt")
  sink(summary_file)
  
  cat("\n=== SUMMARY OF MODEL RESULTS ===\n\n")
  
  for (i in 1:nrow(results)) {
    outcome_var <- results$Outcome[i]
    
    cat("MODEL FOR:", toupper(outcome_var), "\n")
    cat("Model type:", results$Model_Type[i], "\n")
    cat("Pseudo-R²:", round(results$Pseudo_R2[i], 4), "   RMSE:", round(results$RMSE[i], 4), "\n")
    
    # Parse coefficients string into a data frame
    coef_str <- results$Coefficients[i]
    coef_parts <- strsplit(coef_str, ", ")[[1]]
    
    coef_names <- sapply(strsplit(coef_parts, " = "), function(x) x[1])
    coef_values <- as.numeric(sapply(strsplit(coef_parts, " = "), function(x) x[2]))
    
    coefs <- data.frame(
      Variable = coef_names,
      Coefficient = coef_values,
      stringsAsFactors = FALSE
    )
    
    # Remove intercept for display
    coefs <- coefs[coefs$Variable != "(Intercept)",]
    
    # Filter to keep only non-zero coefficients
    coefs <- coefs[abs(coefs$Coefficient) > 1e-5, ]
    
    # Skip if no non-zero coefficients remain
    if (nrow(coefs) == 0) {
      cat("⚠️ No non-zero coefficients found for this model.\n")
      next
    }
    
    # Sort by absolute coefficient value
    coefs$AbsCoef <- abs(coefs$Coefficient)
    coefs <- coefs[order(coefs$AbsCoef, decreasing = TRUE),]
    
    # Calculate incidence rate ratios (exp(coef))
    coefs$IRR <- exp(coefs$Coefficient)
    
    # Add variable groups for plotting
    coefs$Group <- case_when(
      grepl("^A$|^B$|^C$|^D$|^YOI$", coefs$Variable) ~ "Prison Type",
      grepl("^Male$|^Female_", coefs$Variable) ~ "Gender",
      grepl("^Avg_Population$", coefs$Variable) ~ "Population",
      grepl("^Overcrowded_", coefs$Variable) ~ "Overcrowding Status",
      grepl("^Avg_Occupancy_Proportion_", coefs$Variable) ~ "Occupancy Interaction",
      TRUE ~ "Other"
    )
    
    # Format output
    cat("\nNon-zero coefficients (sorted by importance):\n")
    cat("----------------------------------------------\n")
    cat(sprintf("%-30s %10s %10s\n", "Variable", "Coef", "IRR"))
    cat(sprintf("%-30s %10s %10s\n", "--------", "----", "---"))
    
    for (j in 1:nrow(coefs)) {
      cat(sprintf("%-30s %10.4f %10.4f\n", 
                  coefs$Variable[j], 
                  coefs$Coefficient[j],
                  coefs$IRR[j]))
    }
    
    # Save coefficients to CSV
    coef_csv_file <- file.path(output_dir, paste0(outcome_var, "_coefficients.csv"))
    write.csv(coefs, coef_csv_file, row.names = FALSE)
    
    # Interpretation text output remains the same... (skipping for brevity)
    
    # --------------------------
    # Forest Plot (only for non-zero coefficients)
    # --------------------------
    # Add approximate confidence intervals (for visualization only)
    coefs$se <- pmax(0.1, abs(coefs$Coefficient) * 0.2)  # Larger coefficients get wider intervals
    coefs$Lower_CI <- exp(coefs$Coefficient - 1.96 * coefs$se)
    coefs$Upper_CI <- exp(coefs$Coefficient + 1.96 * coefs$se)
    
    # Reorder factors for plotting
    coefs$Variable <- factor(coefs$Variable, levels = rev(coefs$Variable))
    
    # Create forest plot with white background and colorblind-friendly palette
    forest_plot <- ggplot(coefs, aes(x = IRR, y = Variable, color = Group)) +
      geom_vline(xintercept = 1, linetype = "dashed", color = "gray50") +
      geom_point(size = 4) +
      geom_errorbarh(aes(xmin = Lower_CI, xmax = Upper_CI), height = 0.4, size = 1) +
      scale_x_log10(breaks = c(0.1, 0.5, 1, 2, 5),
                    labels = c("0.1", "0.5", "1", "2", "5")) +
      scale_color_viridis_d(option = "D", begin = 0.1, end = 0.9) +  # Better for colorblindness
      labs(
        title = paste("Effect Sizes for", outcome_var),
        subtitle = paste("Incidence Rate Ratios (non-zero coefficients only)"),
        x = "Incidence Rate Ratio (IRR)",
        y = ""
      ) +
      theme_bw() +  # White background with borders
      theme(
        plot.title = element_text(face = "bold", size = 14),
        plot.subtitle = element_text(size = 12),
        legend.position = "bottom",
        panel.grid.minor = element_blank(),
        axis.title = element_text(size = 12, face = "bold"),
        legend.title = element_text(size = 11, face = "bold"),
        legend.text = element_text(size = 10)
      )
    
    # Display the plot
    print(forest_plot)
    
    # Save forest plot
    forest_plot_file <- file.path(output_dir, paste0(outcome_var, "_forest_plot.png"))
    ggsave(forest_plot_file, forest_plot, width = 10, height = 8, dpi = 300, bg = "white")
    
    # --------------------------
    # Effect Size Plot (only for non-zero coefficients)
    # --------------------------
    # Transform coefficients to percentage change for easier interpretation
    coefs$PercentChange <- ifelse(coefs$Coefficient > 0,
                                  (exp(coefs$Coefficient) - 1) * 100,
                                  -(1 - exp(coefs$Coefficient)) * 100)
    
    # Cap extreme values for better visualization
    max_effect <- 200
    coefs$PercentChange_capped <- pmin(pmax(coefs$PercentChange, -max_effect), max_effect)
    
    # Add labels
    coefs$Label <- ifelse(abs(coefs$PercentChange) > max_effect,
                          paste0(ifelse(coefs$PercentChange > 0, ">", "<"), max_effect, "%"),
                          paste0(round(coefs$PercentChange, 1), "%"))
    
    # Reorder for this plot
    coefs$Variable <- factor(coefs$Variable, 
                             levels = coefs$Variable[order(coefs$PercentChange_capped)])
    
    effect_plot <- ggplot(coefs, aes(x = PercentChange_capped, y = Variable, fill = Group)) +
      geom_col() +
      geom_vline(xintercept = 0, linetype = "dashed", color = "gray50") +
      geom_text(aes(label = Label, 
                    x = ifelse(PercentChange_capped > 0, 
                               PercentChange_capped + 10, 
                               PercentChange_capped - 10)),
                hjust = ifelse(coefs$PercentChange_capped > 0, 0, 1),
                size = 3.5) +
      scale_x_continuous(limits = c(-max_effect - 50, max_effect + 50)) +
      scale_fill_viridis_d(option = "D", begin = 0.1, end = 0.9) +  # Better for colorblindness
      labs(
        title = paste("Percentage Change in", outcome_var),
        subtitle = "Estimated effect size (non-zero coefficients only)",
        x = "Percentage Change (%)",
        y = ""
      ) +
      theme_bw() +  # White background with borders
      theme(
        plot.title = element_text(face = "bold", size = 14),
        plot.subtitle = element_text(size = 12),
        legend.position = "bottom",
        panel.grid.minor = element_blank(),
        axis.title = element_text(size = 12, face = "bold"),
        legend.title = element_text(size = 11, face = "bold"),
        legend.text = element_text(size = 10)
      )
    
    # Display the plot
    print(effect_plot)
    
    # Save effect plot
    effect_plot_file <- file.path(output_dir, paste0(outcome_var, "_effect_plot.png"))
    ggsave(effect_plot_file, effect_plot, width = 10, height = 8, dpi = 300, bg = "white")
    
    # --------------------------
    # Occupancy Interaction Plot (if applicable, only non-zero interactions)
    # --------------------------
    interact_vars <- coefs$Variable[grep("Avg_Occupancy_Proportion_", coefs$Variable)]
    
    if (length(interact_vars) > 0) {
      # Create a data frame for interaction visualization
      occupancy_range <- seq(0.7, 1.5, by = 0.05)
      int_data <- data.frame()
      
      for (var in interact_vars) {
        base_var <- gsub("Avg_Occupancy_Proportion_", "", var)
        int_coef <- coefs$Coefficient[coefs$Variable == var]
        
        # Get main effect if it exists
        main_effect <- 0
        if (base_var %in% coefs$Variable) {
          main_effect <- coefs$Coefficient[coefs$Variable == base_var]
        }
        
        # Calculate multiplicative effect for each occupancy level
        for (occ in occupancy_range) {
          effect <- exp(main_effect + int_coef * occ)
          int_data <- rbind(int_data, data.frame(
            Variable = base_var,
            Occupancy = occ,
            Effect = effect
          ))
        }
      }
      
      # Plot interaction effects with improved design
      int_plot <- ggplot(int_data, aes(x = Occupancy, y = Effect, color = Variable)) +
        # Add shaded regions for different occupancy levels
        annotate("rect", xmin = 0, xmax = 1, ymin = -Inf, ymax = Inf, 
                 alpha = 0.1, fill = "green") +
        annotate("rect", xmin = 1, xmax = 1.2, ymin = -Inf, ymax = Inf, 
                 alpha = 0.1, fill = "yellow") +
        annotate("rect", xmin = 1.2, xmax = max(occupancy_range), ymin = -Inf, ymax = Inf, 
                 alpha = 0.1, fill = "red") +
        # Add text labels for the regions
        annotate("text", x = 0.85, y = max(int_data$Effect) * 0.9, 
                 label = "Below capacity", size = 3.5, color = "darkgreen") +
        annotate("text", x = 1.1, y = max(int_data$Effect) * 0.9, 
                 label = "Medium overcrowding", size = 3.5, color = "darkgoldenrod4") +
        annotate("text", x = 1.35, y = max(int_data$Effect) * 0.9, 
                 label = "High overcrowding", size = 3.5, color = "darkred") +
        geom_line(size = 1.2) +
        geom_hline(yintercept = 1, linetype = "dashed", color = "gray50") +
        scale_y_log10(breaks = c(0.1, 0.2, 0.5, 1, 2, 5, 10)) +
        scale_x_continuous(breaks = seq(0.7, 1.5, by = 0.1)) +
        scale_color_viridis_d(option = "D", begin = 0.1, end = 0.9) +  # Better for colorblindness
        labs(
          title = paste("Effect of Occupancy by Prison Type on", outcome_var),
          subtitle = "How the impact of occupancy varies across prison types",
          x = "Occupancy Proportion",
          y = "Relative Risk",
          color = "Prison Type"
        ) +
        theme_bw() +  # White background with borders
        theme(
          plot.title = element_text(face = "bold", size = 14),
          plot.subtitle = element_text(size = 12),
          legend.position = "bottom",
          panel.grid.minor = element_blank(),
          axis.title = element_text(size = 12, face = "bold"),
          legend.title = element_text(size = 11, face = "bold"),
          legend.text = element_text(size = 10)
        )
      
      # Display the plot
      print(int_plot)
      
      # Save interaction plot
      int_plot_file <- file.path(output_dir, paste0(outcome_var, "_interaction_plot.png"))
      ggsave(int_plot_file, int_plot, width = 10, height = 6, dpi = 300, bg = "white")
    }
  }
  
  # Close the text file
  sink()
  
  # Also save the full results table
  results_file <- file.path(output_dir, "model_results_table.csv")
  write.csv(results, results_file, row.names = FALSE)
  
  cat("✅ All model results and plots saved to:", output_dir, "\n")
}
format_model_results(results)

summary(results$Pseudo_R2)
summary(results$NonZero_Coefficients)
table(results$Model_Type)
table(is.na(results$AIC))

