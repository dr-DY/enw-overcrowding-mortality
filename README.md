# Prison Mortality and Overcrowding Analysis

An analysis of prison mortality rates in England and Wales, examining the relationship between prison conditions and deaths in custody.

## Project Overview

This project analyses mortality data in England and Wales prisons from 2014-2024, with a focus on understanding how prison conditions—particularly overcrowding—correlate with different types of deaths in custody. The analysis includes statistical modelling to quantify these relationships and provides projections of mortality rates for 2024-2029.

## Methodology

The analysis follows these key steps:

1. **Data Collection**: Prison population data is scraped from Ministry of Justice monthly publications, extracting information from various file formats.

2. **Data Processing**: 
   - Standardisation of prison population metrics
   - Classification of death types (natural causes, self-inflicted, homicide, other)
   - Calculation of age-specific death rates

3. **Statistical Modelling**:
   - Negative binomial regression with elastic net regularisation
   - Analyses of different prison categories and overcrowding thresholds
   - Interaction modelling between occupancy and prison characteristics

4. **Predictive Analysis**:
   - Bootstrap resampling to generate robust confidence intervals
   - Projections based on expected prison population growth

## Repository Contents

- **Jupyter Notebooks**: Data extraction, processing, and exploratory analysis
- **R Scripts**: Statistical modelling and predictions
- **Functions**: Python modules for data processing and visualisation
- **Output**: Processed data and analytical results

## Key Outputs

The project produces:

- Statistical models quantifying the impact of prison conditions on mortality
- Visualisations of death rate trends and prison occupancy
- Projections of expected deaths under different population scenarios

## License

This repository is provided for research and educational purposes. Distribution and use of the code and methodology are permitted with appropriate attribution.

## Citation

If you use or reference this work, please cite it as:

Yukhnenko, D. (2025). Overcrowding and mortality in English and Welsh prisons. [Source code]. GitHub. https://github.com/dr-DY/enw-overcrowding-mortality.git