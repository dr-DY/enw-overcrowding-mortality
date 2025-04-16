library(dplyr)
library(openxlsx)

# Load the dataset
data <- read.xlsx("Output/For_analysis/merged_data_monthly_2014_2024.xlsx")

# Step 1: Filter for observations in 2024
data_2024 <- data %>% filter(Year == 2024)

# Step 2: Calculate mean population for each prison in 2024
mean_pop_2024 <- data_2024 %>%
  group_by(Prison_name) %>%
  summarise(Mean_Population = mean(Population, na.rm = TRUE)) %>%
  ungroup()

print(paste0("Number of prisons in 2024: ",length(mean_pop_2024$Prison_name)))

# Step 3: Get the latest observation per prison in 2024
latest_2024_obs <- data_2024 %>%
  group_by(Prison_name) %>%
  filter(Report_Date == max(Report_Date, na.rm = TRUE)) %>%
  slice(1) %>%  # In case of duplicates
  ungroup()

# Step 4: Assign categories using the classification logic
latest_2024_obs$PrisonType <- sapply(1:nrow(latest_2024_obs), function(i) {
  row <- latest_2024_obs[i, ]
  is_A <- row$A == 1
  is_B <- row$B == 1
  is_C <- row$C == 1
  is_YOI <- row$YOI == 1
  is_Female_closed <- row$Female_closed == 1
  is_Female_open <- row$Female_open == 1
  
  if (is_A) return("A")
  else if (is_B && is_YOI) return("B+YOI")
  else if (is_B && is_Female_closed) return("B Female (Closed)")
  else if (is_B) return("B")
  else if (is_C && is_YOI) return("C+YOI")
  else if (is_C) return("C")
  else if (is_YOI && is_Female_closed) return("YOI Female (Closed)")
  else if (is_YOI) return("YOI")
  else if (is_Female_closed) return("Female (Closed)")
  else if (is_Female_open) return("Female (Open)")
  else return("D")
})

# Step 5: Merge with average population
prison_pop_by_type <- latest_2024_obs %>%
  left_join(mean_pop_2024, by = "Prison_name") %>%
  group_by(PrisonType) %>%
  summarise(Total_Population = sum(Mean_Population, na.rm = TRUE)) %>%
  arrange(desc(Total_Population))

# Show the result
print(prison_pop_by_type)
