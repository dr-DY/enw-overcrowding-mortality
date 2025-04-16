library(dplyr)
library(tidyr)
library(stringr)
library(ggplot2)
library(viridis)
library(openxlsx)

# 1. Prepare the IRR + 95% CI Table
compute_irr_ci <- function(coef) {
  se <- max(0.1, abs(coef * 0.2))  # Conservative se
  irr <- exp(coef)
  lower <- exp(coef - 1.96 * se)
  upper <- exp(coef + 1.96 * se)
  return(sprintf("%.2f (%.2f–%.2f)", irr, lower, upper))
}

# Initialize output list
irr_ci_list <- list()

# Loop over results
for (i in 1:nrow(results)) {
  outcome <- results$Outcome[i]
  coef_string <- results$Coefficients[i]
  selected_vars <- unlist(strsplit(results$Selected_Variables[i], ", "))
  
  # Parse coefficients
  coef_parts <- unlist(strsplit(coef_string, ", "))
  coef_df <- do.call(rbind, lapply(coef_parts, function(part) {
    kv <- strsplit(part, " = ")[[1]]
    if (length(kv) == 2) {
      data.frame(
        Variable = kv[1],
        Coefficient = as.numeric(kv[2]),
        stringsAsFactors = FALSE
      )
    } else NULL
  }))
  
  # Filter only selected variables (drop intercepts, drop shrunk-out)
  coef_df <- coef_df %>%
    filter(Variable %in% selected_vars, Variable != "(Intercept)")
  
  # Compute IRR and CI
  coef_df$IRR_CI <- sapply(coef_df$Coefficient, compute_irr_ci)
  irr_ci_list[[outcome]] <- setNames(coef_df$IRR_CI, coef_df$Variable)
}

# Combine into dataframe
all_vars <- unique(unlist(lapply(irr_ci_list, names)))
irr_ci_df <- data.frame(Variable = all_vars, stringsAsFactors = FALSE)

for (outcome in names(irr_ci_list)) {
  irr_ci_df[[outcome]] <- irr_ci_list[[outcome]][match(irr_ci_df$Variable, names(irr_ci_list[[outcome]]))]
}

irr_ci_df[is.na(irr_ci_df)] <- "-"

# Rename outcomes
colnames(irr_ci_df)[-1] <- c(
  "Total Deaths", "Homicides", "Self-Inflicted", 
  "Natural Deaths", "Other Deaths", "Other Deaths (incl. Homicides)"
)

# Rename rows
row_rename_map <- c(
  "A" = "Category A prison",
  "B" = "Category B prison",
  "C" = "Category C prison",
  "D" = "Category D prison",
  "YOI" = "Youth Offender Institution (YOI)",
  "Male" = "Male prison",
  "Female_closed" = "Female prison (closed)",
  "Mixed" = "Mixed male and female",
  "Female_open" = "Female prison (open)",
  "Avg_Population" = "Average Prison Population",
  "Well_below_capacity" = "Well below capacity (<95%)",
  "Close_to_capacity" = "Close to capacity (95–100%)",
  "Overcrowded_light" = "Overcrowding (101–110%)",
  "Overcrowded_medium" = "Overcrowding (111–120%)",
  "Overcrowded_high" = "Overcrowding (>120%)",
  "Avg_Occupancy_Proportion_A" = "Average Occupancy Proportion * Category A",
  "Avg_Occupancy_Proportion_B" = "Average Occupancy Proportion * Category B",
  "Avg_Occupancy_Proportion_C" = "Average Occupancy Proportion * Category C",
  "Avg_Occupancy_Proportion_D" = "Average Occupancy Proportion * Category D",
  "Avg_Occupancy_Proportion_YOI" = "Average Occupancy Proportion * YOI",
  "Avg_Occupancy_Proportion_Male" = "Average Occupancy Proportion * Male prison",
  "Avg_Occupancy_Proportion_Female_closed" = "Average Occupancy Proportion * Female prison (closed)"
)


# Keep and rename selected variables
irr_ci_df <- irr_ci_df[irr_ci_df$Variable %in% names(row_rename_map), ]
irr_ci_df$Variable <- row_rename_map[irr_ci_df$Variable]

# Save to Excel
openxlsx::write.xlsx(
  irr_ci_df, 
  file = "Output/Models_output/IRR_CI_Table_Pretty.xlsx", 
  rowNames = FALSE
)




# 2. Generate forest plots
irr_long <- irr_ci_df %>%
  pivot_longer(cols = -Variable, names_to = "Outcome", values_to = "IRR_CI") %>%
  filter(IRR_CI != "-") %>%
  mutate(
    Estimate = as.numeric(str_extract(IRR_CI, "^[0-9.]+")),
    Lower = as.numeric(str_extract(IRR_CI, "(?<=\\().+?(?=–)")),
    Upper = as.numeric(str_extract(IRR_CI, "(?<=–).+?(?=\\))"))
  ) %>%
  filter(!is.na(Estimate))

# Loop and plot
for (outcome_name in unique(irr_long$Outcome)) {
  df_sub <- irr_long %>%
    filter(Outcome == outcome_name) %>%
    arrange(desc(Estimate)) %>%
    mutate(Variable = factor(Variable, levels = rev(Variable)))  # High IRR on top
  
  n_vars <- nrow(df_sub)
  
  p <- ggplot(df_sub, aes(x = Estimate, y = Variable)) +
    geom_point(size = 3, color = viridis(1, begin = 0.2)) +
    geom_errorbarh(aes(xmin = Lower, xmax = Upper), height = 0.3, color = viridis(1, begin = 0.2)) +
    geom_vline(xintercept = 1, linetype = "dashed", color = "gray40") +
    scale_x_log10(
      limits = c(0.1, 4), 
      breaks = c(0.12, 0.25, 0.5, 1, 2, 4)
    ) +
    labs(
      title = paste("Forest Plot for", outcome_name),
      x = "Incidence Rate Ratio (log scale)",
      y = NULL
    ) +
    theme_bw(base_size = 14) +
    theme(
      panel.grid.minor = element_blank(),
      plot.title = element_text(hjust = 0.5)
    )
  
  ggsave(
    filename = paste0("Output/Models_output/forest_", outcome_name, ".png"),
    plot = p,
    width = 8, 
    height = 1.1 + 0.4 * n_vars,  # Dynamic height
    dpi = 300
  )
}

# View the pretty table
print(irr_ci_df)



# 3. Generate model performance summary
# Generate summary table
summary_table <- results %>%
  dplyr::select(Outcome, Pseudo_R2, Selected_Variables) %>%
  dplyr::mutate(
    Outcome = dplyr::recode(
      Outcome,
      "Adjusted_Deaths" = "Total Deaths",
      "Adjusted_Homicide" = "Homicides",
      "Adjusted_SelfInflicted" = "Self-Inflicted",
      "Adjusted_Natural" = "Natural Deaths",
      "Adjusted_Other" = "Other Deaths",
      "Adjusted_Other_inclHomicide" = "Other Deaths (incl. Homicides)"
    ),
    No_Selected_Variables = sapply(strsplit(Selected_Variables, ",\\s*"), length)
  ) %>%
  dplyr::rename(
    `Outcome Measure` = Outcome,
    `Pseudo-R²` = Pseudo_R2,
    `No. Selected Variables` = No_Selected_Variables
  ) %>%
  dplyr::select(`Outcome Measure`, `Pseudo-R²`, `No. Selected Variables`)

# Print the summary table
print(summary_table)

# Save to Excel if needed
openxlsx::write.xlsx(summary_table, "Output/Models_output/Model_Summary_Table.xlsx", rowNames = FALSE)



