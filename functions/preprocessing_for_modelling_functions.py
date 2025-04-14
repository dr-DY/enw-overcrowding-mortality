import pandas as pd
import numpy as np
from datetime import datetime
import re

def merge_prison_deaths_data(prison_file, deaths_file):
    """
    Merge prison capacity data with deaths in custody data,
    ensuring one row per prison per month with summed death counts
    
    Parameters:
    -----------
    prison_file : str
        Path to prison capacity CSV file
    deaths_file : str
        Path to deaths in custody Excel file
        
    Returns:
    --------
    merged_df : pandas DataFrame
        Merged dataset with prison capacity and deaths information
    """
    # Load the datasets
    prison_df = pd.read_csv(prison_file)
    deaths_df = pd.read_excel(deaths_file)
    
    # Clean and prepare prison capacity data
    prison_df['Report_Date'] = pd.to_datetime(prison_df['Report_Date'])
    prison_df['Year'] = prison_df['Report_Date'].dt.year
    prison_df['Month'] = prison_df['Report_Date'].dt.month
    
    # Calculate occupancy percentage and categorize
    prison_df['Occupancy_Percentage'] = (prison_df['Population *'] / prison_df['In Use CNA']) * 100
    prison_df['Overcrowding_Status'] = pd.cut(
        prison_df['Occupancy_Percentage'],
        bins=[0, 90, 100, float('inf')],
        labels=['Below Capacity (<90%)', 'At Capacity (90-100%)', 'Overcrowded (>100%)']
    )
    
    # Clean and prepare deaths data
    deaths_df['Date'] = pd.to_datetime(deaths_df['Date'])
    deaths_df['Year'] = deaths_df['Year'].astype(int)
    deaths_df['Month'] = deaths_df['Month'].astype(int)
    
    # Standardize death types (case-insensitive matching)
    deaths_df['type_of_death'] = deaths_df['type_of_death'].str.lower()
    
    # Standardize "Natural causes" variations
    natural_pattern = r'natural\s*causes?'
    deaths_df.loc[deaths_df['type_of_death'].str.contains(natural_pattern, regex=True, na=False), 'type_of_death'] = 'Natural causes'
    
    # Standardize "Self-inflicted" variations
    self_inflicted_pattern = r'self.?inflicted'
    deaths_df.loc[deaths_df['type_of_death'].str.contains(self_inflicted_pattern, regex=True, na=False), 'type_of_death'] = 'Self-inflicted'
    
    # Collapse all "Other" categories into one
    other_pattern = r'other'
    deaths_df.loc[deaths_df['type_of_death'].str.contains(other_pattern, regex=True, na=False), 'type_of_death'] = 'Other'
    
    # Make death types title case for better presentation
    deaths_df['type_of_death'] = deaths_df['type_of_death'].str.title()
    
    # Ensure prison names match between datasets
    deaths_df.rename(columns={'Prison': 'Prison Name'}, inplace=True)
    
    # Print unique death types to verify standardization
    print("Standardized death types:", deaths_df['type_of_death'].unique())
    
    # Aggregate death incidents by prison, year, month - summing all deaths of any type
    deaths_by_month = deaths_df.groupby(['Prison Name', 'Year', 'Month']).agg(
        Total_Deaths=('incidents', 'sum')
    ).reset_index()
    
    # Also aggregate by death type to keep that information
    deaths_by_type = deaths_df.groupby(['Prison Name', 'Year', 'Month', 'type_of_death']).agg(
        death_count=('incidents', 'sum')
    ).reset_index()
    
    # Create pivot table for death types
    deaths_pivot = deaths_by_type.pivot_table(
        index=['Prison Name', 'Year', 'Month'],
        columns='type_of_death',
        values='death_count',
        fill_value=0
    ).reset_index()
    
    # Merge the pivot table with the monthly totals to ensure we have both
    # the breakdown by type and the total in one DataFrame
    deaths_complete = pd.merge(
        deaths_pivot,
        deaths_by_month,
        on=['Prison Name', 'Year', 'Month'],
        how='left'
    )
    
    # Merge with prison data - this ensures one row per prison per month
    merged_df = pd.merge(
        prison_df,
        deaths_complete,
        how='left',
        on=['Prison Name', 'Year', 'Month']
    )
    
    # Fill NA values for death counts with 0
    death_cols = [col for col in merged_df.columns if col not in prison_df.columns]
    merged_df[death_cols] = merged_df[death_cols].fillna(0)
    
    # Verify we have one row per prison per month
    counts = merged_df.groupby(['Prison Name', 'Year', 'Month']).size().reset_index(name='count')
    if (counts['count'] > 1).any():
        print("WARNING: Some prison-month combinations have multiple rows")
        print(counts[counts['count'] > 1])
    else:
        print("Verified: One row per prison per month")
    
    return merged_df

# Function to create a summary of deaths by overcrowding status
def analyze_deaths_by_overcrowding(merged_df):
    """
    Analyze death rates by prison overcrowding status
    
    Parameters:
    -----------
    merged_df : pandas DataFrame
        Merged dataset with prison capacity and deaths information
        
    Returns:
    --------
    summary_df : pandas DataFrame
        Summary statistics of deaths by overcrowding status
    death_types_df : pandas DataFrame
        Breakdown of death types by overcrowding status
    """
    # Group by overcrowding status for overall statistics
    summary = merged_df.groupby('Overcrowding_Status').agg(
        prison_months=('Prison Name', 'count'),
        total_deaths=('Total_Deaths', 'sum'),
        total_population=('Population *', 'sum')
    )
    
    # Calculate death rate per 1,000 prisoners
    summary['death_rate_per_1000'] = (summary['total_deaths'] / summary['total_population']) * 1000
    
    # Calculate percentage of prison-months in each category
    summary['percent_of_prison_months'] = (summary['prison_months'] / summary['prison_months'].sum()) * 100
    
    # Add total row
    total_row = pd.Series({
        'prison_months': summary['prison_months'].sum(),
        'total_deaths': summary['total_deaths'].sum(),
        'total_population': summary['total_population'].sum(),
        'death_rate_per_1000': (summary['total_deaths'].sum() / summary['total_population'].sum()) * 1000,
        'percent_of_prison_months': 100.0
    }, name='Total')
    
    summary_df = pd.concat([summary, pd.DataFrame([total_row])])
    
    # Analyze deaths by type and overcrowding status
    death_types = [col for col in merged_df.columns 
                  if col not in ['Prison Name', 'In Use CNA', 'Population *', 
                                'Operational Capacity', 'Baseline CNA', 'Report_Date',
                                'Year', 'Month', 'Occupancy_Percentage', 'Overcrowding_Status',
                                'Total_Deaths'] and col not in merged_df.select_dtypes(include=['datetime64']).columns]
    
    if death_types:
        # Create a DataFrame for death types by overcrowding status
        death_types_data = []
        
        for status in merged_df['Overcrowding_Status'].dropna().unique():
            status_df = merged_df[merged_df['Overcrowding_Status'] == status]
            population = status_df['Population *'].sum()
            
            for death_type in death_types:
                death_count = status_df[death_type].sum()
                rate_per_1000 = (death_count / population) * 1000 if population > 0 else 0
                percent_of_deaths = (death_count / status_df['Total_Deaths'].sum()) * 100 if status_df['Total_Deaths'].sum() > 0 else 0
                
                death_types_data.append({
                    'Overcrowding_Status': status,
                    'Death_Type': death_type,
                    'Count': death_count,
                    'Rate_per_1000': rate_per_1000,
                    'Percent_of_Deaths': percent_of_deaths
                })
        
        # Add total row for each death type
        for death_type in death_types:
            total_count = merged_df[death_type].sum()
            total_population = merged_df['Population *'].sum()
            total_rate = (total_count / total_population) * 1000 if total_population > 0 else 0
            total_percent = (total_count / merged_df['Total_Deaths'].sum()) * 100 if merged_df['Total_Deaths'].sum() > 0 else 0
            
            death_types_data.append({
                'Overcrowding_Status': 'Total',
                'Death_Type': death_type,
                'Count': total_count,
                'Rate_per_1000': total_rate,
                'Percent_of_Deaths': total_percent
            })
        
        death_types_df = pd.DataFrame(death_types_data)
    else:
        death_types_df = pd.DataFrame()
    
    return summary_df, death_types_df

# Function to run the complete analysis
def analyze_prison_deaths_and_overcrowding(prison_file, deaths_file):
    """
    Complete workflow to merge data and analyze deaths by overcrowding status
    
    Parameters:
    -----------
    prison_file : str
        Path to prison capacity CSV file
    deaths_file : str
        Path to deaths in custody Excel file
        
    Returns:
    --------
    merged_df : pandas DataFrame
        Merged dataset with prison capacity and deaths information
    summary_df : pandas DataFrame
        Summary statistics of deaths by overcrowding status
    death_types_df : pandas DataFrame
        Breakdown of death types by overcrowding status
    """
    # Merge the datasets
    merged_df = merge_prison_deaths_data(prison_file, deaths_file)
    
    # Analyze deaths by overcrowding status
    summary_df, death_types_df = analyze_deaths_by_overcrowding(merged_df)
    
    return merged_df, summary_df, death_types_df

# Example usage
# merged_data, summary, death_types = analyze_prison_deaths_and_overcrowding(
#     'Output/combined_prison_data.csv', 
#     'Data/deaths_in_custody_by_prison.xlsx'
# )














import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Define the observation period
start_period = "10-2014"
end_period = "09-2024"

# Parse the prison information from the provided data
def create_prison_dataframe():
    # Manually create the dataframe from the provided prison list. Only listing prisons of interest
    # Exluding immigration center and prisons that closed by that time. The list is based on population reporting
    prison_names = ['Altcourse', 'Ashfield', 'Askham Grange', 'Aylesbury', 'Bedford', 'Belmarsh', 
                  'Birmingham', 'Blantyre House', 'Brinsford', 'Bristol', 'Brixton', 'Bronzefield', 
                  'Buckley Hall', 'Bullingdon', 'Bure', 'Cardiff', 'Channings Wood', 'Chelmsford', 
                  'Coldingley', 'Cookham Wood', 'Dartmoor', 'Deerbolt', 'Doncaster', 'Dovegate', 
                  'Downview', 'Drake Hall', 'Durham', 'East Sutton Park', 'Eastwood Park', 
                  'Elmley (Sheppey)', 'Erlestoke', 'Exeter', 'Featherstone', 'Feltham', 'Ford', 
                  'Forest Bank', 'Foston Hall', 'Frankland', 'Full Sutton', 'Garth', 'Gartree', 
                  'Glen Parva', 'Grendon / Springhill', 'Guys Marsh', 'Hatfield', 'Haverigg',  'Hewell', 
                  'High Down', 'Highpoint (North and South)', 'Hindley', 'Hollesley Bay', 'Holloway', 
                  'Holme House', 'Hull', 'Humber', 'Huntercombe', 'Isis', 'Isle of Wight', 'Kennet', 
                  'Kirkham', 'Kirklevington Grange', 'Lancaster Farms', 'Leeds', 'Leicester', 'Lewes', 
                  'Leyhill', 'Lincoln', 'Lindholme', 'Littlehey', 'Liverpool', 'Long Lartin', 
                  'Low Newton', 'Lowdham Grange', 'Maidstone', 'Manchester', 'Moorland', 'Moorland / Hatfield',  
                  'Mount', 'New Hall', 'North Sea Camp', 'Northumberland', 'Norwich', 'Nottingham', 
                  'Oakwood', 'Onley', 'Parc', 'Pentonville', 'Peterborough (Male & Female)', 'Portland', 
                  'Preston', 'Ranby', 'Risley', 'Rochester', 'Rye Hill', 'Send', 'Stafford', 
                  'Standford Hill (Sheppey)', 'Stocken', 'Stoke Heath', 'Styal', 'Sudbury', 
                  'Swaleside (Sheppey)', 'Swansea', 'Swinfen Hall', 'Thameside', 'Thorn Cross', 
                  'Usk / Prescoed', 'Wakefield', 'Wandsworth', 'Warren Hill', 'Wayland', 'Wealstun', 
                  'Werrington', 'Wetherby', 'Whatton', 'Whitemoor', 'Winchester', 'Woodhill', 
                  'Wormwood Scrubs', 'Wymott', 'Haslar', 'Dover', 'Berwyn', 
                  'The Verne', 'Morton Hall', 'Five Wells', 'Fosse Way']
    
    # Create an empty dataframe
    columns = [
        'Prison_name', 'start_period', 'end_period', 
        'A', 'B', 'C', 'D', 'YOI', 'Closed',
        'Male', 'Female', 'Mixed', 'Notes'
    ]
    df = pd.DataFrame(columns=columns)
    
    return df, prison_names

# Initialize the dataframe with information from paste.txt and additional sources
def initialize_prison_data(df, prison_names):
    # Base information with corrected categorizations based on all sources
    prison_data = [
        # Original data from paste.txt with corrections
        {"Prison_name": "Altcourse", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Operated by G4S; houses adults and young offenders"},
        {"Prison_name": "Ashfield", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Operated by Serco; specializes in adult sex offenders"},
        {"Prison_name": "Askham Grange", "Security": "Open", "Gender": "Female", "YOI": False, "Notes": "Open prison for adults and young offenders"},
        {"Prison_name": "Aylesbury", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Young Offender Institution"},
        {"Prison_name": "Bedford", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Houses adults and young offenders"},
        {"Prison_name": "Belmarsh", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "High-security prison; houses high-profile inmates"},
        # Empty Berwyn entry - will be handled by events
        {"Prison_name": "Birmingham", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Previously known as Winson Green"},
        {"Prison_name": "Blantyre House", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Resettlement prison"},
        {"Prison_name": "Brinsford", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Young Offender Institution"},
        {"Prison_name": "Bristol", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Houses adults and young offenders"},
        {"Prison_name": "Brixton", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Functions as a training establishment"},
        {"Prison_name": "Bronzefield", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Operated by Sodexo Justice Services; closed women's prison - houses adults and young offenders"},
        {"Prison_name": "Buckley Hall", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Bullingdon", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison with some C prisoners"},
        {"Prison_name": "Bure", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Specializes in sex offenders"},
        {"Prison_name": "Cardiff", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Channings Wood", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Offers Sex Offender Treatment Programme (SOTP)"},
        {"Prison_name": "Chelmsford", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Houses adults and young offenders"},
        {"Prison_name": "Coldingley", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Functions as a training prison"},
        {"Prison_name": "Cookham Wood", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Young Offender Institution for juveniles (15-18)"},
        {"Prison_name": "Dartmoor", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Functions as a training prison"},
        {"Prison_name": "Deerbolt", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Young Offender Institution"},
        {"Prison_name": "Doncaster", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Operated by Serco; houses adults, young offenders, and sex offenders"},
        {"Prison_name": "Dovegate", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Operated by Serco; functions as a training prison"},
        {"Prison_name": "Downview", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison (reopened in 2016)"},
        {"Prison_name": "Drake Hall", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison; specializes in foreign nationals"},
        {"Prison_name": "Durham", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Houses adults and young offenders on remand"},
        {"Prison_name": "East Sutton Park", "Security": "Open", "Gender": "Female", "YOI": False, "Notes": "Open women's prison"},
        {"Prison_name": "Eastwood Park", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison"},
        {"Prison_name": "Elmley (Sheppey)", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Erlestoke", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Exeter", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Houses adults and young offenders"},
        {"Prison_name": "Featherstone", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Functions as a training establishment"},
        {"Prison_name": "Feltham", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Young Offender Institution"},
        {"Prison_name": "Ford", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Forest Bank", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Operated by Sodexo Justice Services; houses adults and young offenders"},
        # Empty Fosse Way entry - will be handled by events
        {"Prison_name": "Foston Hall", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison; houses adults and young offenders"},
        # Empty Five Wells entry - will be handled by events
        {"Prison_name": "Frankland", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "High-security prison; houses Category A High Risk and Category B adult males"},
        {"Prison_name": "Full Sutton", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "High-security prison; houses Category A prisoners"},
        {"Prison_name": "Garth", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B training establishment"},
        {"Prison_name": "Gartree", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B training prison"},
        {"Prison_name": "Glen Parva", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Young Offender Institution (18-21)"},
        {"Prison_name": "Grendon / Springhill", "Security": "B, D", "Gender": "Male", "YOI": False, "Notes": "Grendon is Cat B therapeutic community, Springhill is Cat D open"},
        {"Prison_name": "Guys Marsh", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Haverigg", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Hewell", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Primarily Category B local (open site closed in 2020)"},
        {"Prison_name": "High Down", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Highpoint (North and South)", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Hindley", "Security": "C", "Gender": "Male", "YOI": True, "Notes": "Former YOI, now Cat C adult men but still holds some young offenders"},
        {"Prison_name": "Hollesley Bay", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Holloway", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison (closed in 2016)"},
        {"Prison_name": "Holme House", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Changed from local (B) to Cat C prison in May 2017"},
        {"Prison_name": "Hull", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Humber", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Huntercombe", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (foreign nationals)"},
        {"Prison_name": "Isis", "Security": "C", "Gender": "Male", "YOI": True, "Notes": "Category C prison with YOI function"},
        {"Prison_name": "Isle of Wight", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Primarily Category B (combining ex-Parkhurst/Albany)"},
        {"Prison_name": "Kennet", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (closed in 2016)"},
        {"Prison_name": "Kirkham", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Kirklevington Grange", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open resettlement prison"},
        {"Prison_name": "Lancaster Farms", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Leeds", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Leicester", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Lewes", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Leyhill", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Lincoln", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Lindholme", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Littlehey", "Security": "C", "Gender": "Male", "YOI": True, "Notes": "Adult side is Cat C, also has YOI side (18-21)"},
        {"Prison_name": "Liverpool", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Long Lartin", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "Category A high security prison"},
        {"Prison_name": "Low Newton", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison"},
        {"Prison_name": "Lowdham Grange", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B prison (privately operated)"},
        {"Prison_name": "Maidstone", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Manchester", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "Category A high security prison (Strangeways)"},
        {"Prison_name": "Moorland / Hatfield", "Security": "C, D", "Gender": "Male", "YOI": False, "Notes": "Moorland is Cat C, Hatfield is Cat D open"},
        {"Prison_name": "Moorland", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (part of Moorland/Hatfield)"},
        {"Prison_name": "Hatfield", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison (part of Moorland/Hatfield)"},
        {"Prison_name": "Mount", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "New Hall", "Security": "Closed", "Gender": "Female", "YOI": True, "Notes": "Closed women's prison (for adult women, plus young offenders)"},
        {"Prison_name": "North Sea Camp", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Northumberland", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C training prison"},
        {"Prison_name": "Norwich", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Nottingham", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Oakwood", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (private)"},
        {"Prison_name": "Onley", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Parc", "Security": "B", "Gender": "Male", "YOI": True, "Notes": "Category B local/training (private) with YOI unit"},
        {"Prison_name": "Pentonville", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Peterborough (Male & Female)", "Security": "B", "Gender": "Mixed", "YOI": False, "Notes": "The only dual-purpose prison in England & Wales"},
        {"Prison_name": "Portland", "Security": "C", "Gender": "Male", "YOI": True, "Notes": "Category C with YOI function for young adults"},
        {"Prison_name": "Preston", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Ranby", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Risley", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Rochester", "Security": "C", "Gender": "Male", "YOI": True, "Notes": "Category C prison with YOI side (18-21)"},
        {"Prison_name": "Rye Hill", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B prison (private, mainly for sex offenders)"},
        {"Prison_name": "Send", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison"},
        {"Prison_name": "Stafford", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (specializes in sex offenders)"},
        {"Prison_name": "Standford Hill (Sheppey)", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Stocken", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Stoke Heath", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Styal", "Security": "Closed", "Gender": "Female", "YOI": False, "Notes": "Closed women's prison (with some open units)"},
        {"Prison_name": "Sudbury", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Swaleside (Sheppey)", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B training prison"},
        {"Prison_name": "Swansea", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Swinfen Hall", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "YOI for young adults (18-25)"},
        {"Prison_name": "Thameside", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison (private)"},
        {"Prison_name": "Thorn Cross", "Security": "D", "Gender": "Male", "YOI": False, "Notes": "Category D open prison"},
        {"Prison_name": "Usk / Prescoed", "Security": "C, D", "Gender": "Male", "YOI": False, "Notes": "Usk is Cat C, Prescoed is Cat D open"},
        {"Prison_name": "Wakefield", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "Category A high security prison"},
        {"Prison_name": "Wandsworth", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Warren Hill", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "Specialized juvenile/young adult site"},
        {"Prison_name": "Wayland", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Wealstun", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Werrington", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "YOI (15-18)"},
        {"Prison_name": "Wetherby", "Security": "YOI", "Gender": "Male", "YOI": True, "Notes": "YOI (15-18)"},
        {"Prison_name": "Whatton", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (sex offenders)"},
        {"Prison_name": "Whitemoor", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "Category A high security prison"},
        {"Prison_name": "Winchester", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Woodhill", "Security": "A", "Gender": "Male", "YOI": False, "Notes": "Category A high security prison"},
        {"Prison_name": "Wormwood Scrubs", "Security": "B", "Gender": "Male", "YOI": False, "Notes": "Category B local prison"},
        {"Prison_name": "Wymott", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison"},
        {"Prison_name": "Haslar", "Security": "N/A", "Gender": "Male", "YOI": False, "Notes": "Former Immigration Removal Centre"},
        {"Prison_name": "Dover", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Historically Cat C (later closed / IRC)"},
        {"Prison_name": "Berwyn", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Opened February 2017, largest prison in the UK"},
        {"Prison_name": "The Verne", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison (after reverting from IRC status)"},
        {"Prison_name": "Morton Hall", "Security": "N/A", "Gender": "Female", "YOI": False, "Notes": "Former women's prison, later an IRC"},
        {"Prison_name": "Five Wells", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison operated by G4S, opened March 2022"},
        {"Prison_name": "Fosse Way", "Security": "C", "Gender": "Male", "YOI": False, "Notes": "Category C prison operated by Serco, opened May 2023"}
    ]
    
    # Add rows from the data
    data_rows = []
    for item in prison_data:
        if item["Prison_name"] in prison_names:
            # Skip prisons that opened after 2014 - they'll be added during event processing
            if item["Prison_name"] in ["Berwyn", "Five Wells", "Fosse Way"]:
                continue
                
            # Convert security categories to binary flags
            new_row = {
                'Prison_name': item["Prison_name"],
                'start_period': start_period,
                'end_period': end_period,
                'A': 1 if 'A' in item["Security"] else 0,
                'B': 1 if 'B' in item["Security"] else 0,
                'C': 1 if 'C' in item["Security"] else 0,
                'D': 1 if 'D' in item["Security"] else 0,
                'YOI': 1 if item["YOI"] or 'YOI' in item["Security"] else 0,
                'Closed': 1 if 'Closed' in item["Security"] else 0,
                'Male': 1 if item["Gender"] == "Male" else 0,
                'Female': 1 if item["Gender"] == "Female" else 0,
                'Mixed': 1 if item["Gender"] == "Mixed" else 0,
                'Notes': item["Notes"]
            }
            data_rows.append(new_row)
    
    # Create a new dataframe with the data rows
    new_df = pd.DataFrame(data_rows)
    
    # Combine with the original dataframe
    if not new_df.empty:
        df = pd.concat([df, new_df], ignore_index=True)
    
    return df

# Process the prison events
def process_prison_events(df, prison_names):
    # Prison events data
    events = [
        {"Prison": "Blantyre House", "Date": "03-2015", "Event": "Temporarily closed"},
        {"Prison": "Haslar", "Date": "04-2015", "Event": "Decommissioned places for detainees. Temporarily closed pending re-role"},
        {"Prison": "Dover", "Date": "10-2015", "Event": "Decommissioned places for detainees. Temporarily closed pending re-role"},
        {"Prison": "Downview", "Date": "05-2016", "Event": "Reopened as a female prison"},
        {"Prison": "Holloway", "Date": "06-2016", "Event": "Closed"},
        {"Prison": "Kennet", "Date": "12-2016", "Event": "Closed"},
        {"Prison": "Berwyn", "Date": "02-2017", "Event": "Opened"},
        {"Prison": "Holme House", "Date": "05-2017", "Event": "Changed from local to Cat C prison"},
        {"Prison": "Glen Parva", "Date": "06-2017", "Event": "Closed"},
        {"Prison": "The Verne", "Date": "12-2017", "Event": "Decommissioned places for detainees. Temporarily closed pending re-role"},
        {"Prison": "Birmingham", "Date": "07-2019", "Event": "Changed from private to public"},
        {"Prison": "Five Wells", "Date": "03-2022", "Event": "Opened"},
        {"Prison": "Fosse Way", "Date": "05-2023", "Event": "Opened"}
    ]
    
    # Process each event
    data_rows = []
    
    # First, make a copy of the dataframe to avoid modifying during iteration
    df_copy = df.copy()
    
    for event in events:
        prison_name = event["Prison"]
        event_date = event["Date"]
        event_type = event["Event"]
        
        # Format event date
        event_month, event_year = event_date.split("-")
        event_date_formatted = f"{event_month}-{event_year}"
        
        # Check if the prison exists in our dataframe
        prison_exists = False
        
        for idx, row in df_copy.iterrows():
            if row['Prison_name'] == prison_name:
                prison_exists = True
                
                # Handle specific events
                if "closed" in event_type.lower() or "decommissioned" in event_type.lower():
                    # Update the end period of the existing record
                    df.loc[idx, 'end_period'] = event_date_formatted
                    df.loc[idx, 'Notes'] = f"{df.loc[idx, 'Notes']}; {event_type} in {event_date_formatted}"
                
                elif "reopened" in event_type.lower():
                    # Update the end period of the existing record
                    df.loc[idx, 'end_period'] = event_date_formatted
                    
                    # Create a new record for the reopened prison
                    new_row = row.copy()
                    new_row['start_period'] = event_date_formatted
                    new_row['end_period'] = end_period
                    new_row['Female'] = 1  # Reopened as female prison
                    new_row['Male'] = 0
                    new_row['Notes'] = f"Reopened as a female prison in {event_date_formatted}"
                    data_rows.append(dict(new_row))
                
                elif "opened" in event_type.lower():
                    # For prisons that should only have a single entry from their opening date
                    if prison_name in ["Berwyn", "Five Wells", "Fosse Way"]:
                        df.loc[idx, 'start_period'] = event_date_formatted
                    else:
                        # Create a new record for other opened prisons
                        new_row = {
                            'Prison_name': prison_name,
                            'start_period': event_date_formatted,
                            'end_period': end_period,
                            'A': 0,
                            'B': 0,
                            'C': 1 if prison_name in ["Berwyn", "Five Wells", "Fosse Way"] else 0,
                            'D': 0,
                            'YOI': 0,
                            'Closed': 0,
                            'Male': 1,
                            'Female': 0,
                            'Mixed': 0,
                            'Notes': f"Opened in {event_date_formatted}"
                        }
                        data_rows.append(new_row)
                
                elif "changed" in event_type.lower():
                    # Only create a new record if there's a change in category or gender composition
                    if prison_name == "Holme House" and "local to Cat C" in event_type:
                        # Update the end period of the existing record
                        df.loc[idx, 'end_period'] = event_date_formatted
                        
                        # Create a new record for the changed prison
                        new_row = row.copy()
                        new_row['start_period'] = event_date_formatted
                        new_row['end_period'] = end_period
                        new_row['B'] = 0
                        new_row['C'] = 1
                        new_row['Notes'] = f"{new_row['Notes']}; Changed from local to Cat C prison in {event_date_formatted}"
                        data_rows.append(dict(new_row))
                    
                    elif prison_name == "Birmingham" and "private to public" in event_type:
                        # Just update the notes for change from private to public, no new row
                        df.loc[idx, 'Notes'] = f"{df.loc[idx, 'Notes']}; Changed from private to public in {event_date_formatted}"
        
        # If the prison doesn't exist in our dataframe and it's an "opened" event
        if not prison_exists and "opened" in event_type.lower():
            if prison_name == "Berwyn":
                new_row = {
                    'Prison_name': prison_name,
                    'start_period': event_date_formatted,
                    'end_period': end_period,
                    'A': 0,
                    'B': 0,
                    'C': 1,
                    'D': 0,
                    'YOI': 0,
                    'Closed': 0,
                    'Male': 1,
                    'Female': 0,
                    'Mixed': 0,
                    'Notes': f"Category C prison. Opened in {event_date_formatted}, largest prison in the UK"
                }
            elif prison_name == "Five Wells":
                new_row = {
                    'Prison_name': prison_name,
                    'start_period': event_date_formatted,
                    'end_period': end_period,
                    'A': 0,
                    'B': 0,
                    'C': 1,
                    'D': 0,
                    'YOI': 0,
                    'Closed': 0,
                    'Male': 1,
                    'Female': 0,
                    'Mixed': 0,
                    'Notes': f"Category C prison operated by G4S. Opened in {event_date_formatted}"
                }
            elif prison_name == "Fosse Way":
                new_row = {
                    'Prison_name': prison_name,
                    'start_period': event_date_formatted,
                    'end_period': end_period,
                    'A': 0,
                    'B': 0,
                    'C': 1,
                    'D': 0,
                    'YOI': 0,
                    'Closed': 0,
                    'Male': 1,
                    'Female': 0,
                    'Mixed': 0,
                    'Notes': f"Category C prison operated by Serco. Opened in {event_date_formatted}"
                }
            else:
                new_row = {
                    'Prison_name': prison_name,
                    'start_period': event_date_formatted,
                    'end_period': end_period,
                    'A': 0,
                    'B': 0,
                    'C': 0,
                    'D': 0,
                    'YOI': 0,
                    'Closed': 0,
                    'Male': 1,
                    'Female': 0,
                    'Mixed': 0,
                    'Notes': f"Opened in {event_date_formatted}"
                }
            data_rows.append(new_row)
    
    # Add all new rows at once
    if data_rows:
        new_df = pd.DataFrame(data_rows)
        df = pd.concat([df, new_df], ignore_index=True)
    
    return df

# Main function to create the dataframe
def create_prison_dataset():
    # Create the initial dataframe
    df, prison_names = create_prison_dataframe()
    
    # Initialize with comprehensive prison data
    df = initialize_prison_data(df, prison_names)
    
    # Process prison events
    df = process_prison_events(df, prison_names)
    
    # Sort by prison name and start period
    df = df.sort_values(['Prison_name', 'start_period'])

    # Correcting period for Moorland / Hatfield
    import pandas as pd

    # Assuming your DataFrame is named df

    # Correcting Moorland / Hatfield

    # Update end_period for 'Moorland / Hatfield'
    df.loc[df['Prison_name'] == 'Moorland / Hatfield', 'end_period'] = '01-2015'

    # Update start_period for both 'Moorland' and 'Hatfield'
    df.loc[df['Prison_name'].isin(['Moorland', 'Hatfield']), 'start_period'] = '02-2015'

    
    # Reset index
    df = df.reset_index(drop=True)
    
    return df



import pandas as pd

def update_prison_dataframe(prison_df):
    """
    Update the prison dataframe based on the newest feedback:
    1. Remove the 'Closed' column
    2. Create 'Female_open' and 'Female_closed' columns
    3. Remove Haslar and Morton Hall completely as they were IRCs during the period
    4. Properly mark female prisons
    5. Ensure multi-category sites are correctly marked
    6. Move Notes column to the end
    
    Args:
        prison_df: The existing dataframe with prison data
        
    Returns:
        Updated dataframe with the corrections
    """
    # Make a copy to avoid modifying the original
    df = prison_df.copy()
    
    # 1. Remove the 'Closed' column
    if 'Closed' in df.columns:
        df = df.drop('Closed', axis=1)
    
    # 2. Add 'Female_open' and 'Female_closed' columns with default values of 0
    df['Female_open'] = 0
    df['Female_closed'] = 0
    
    # 3. Remove Haslar and Morton Hall completely from the dataset
    df = df[~df['Prison_name'].isin(['Haslar', 'Morton Hall'])]
    
    # 4. Update female prison classifications
    for idx, row in df.iterrows():
        if row['Female'] == 1:
            df.loc[idx, ['A', 'B', 'C', 'D']] = 0
            
            notes_lower = str(row['Notes']).lower()
            if 'open' in notes_lower and 'closed' not in notes_lower:
                df.loc[idx, 'Female_open'] = 1
            else:
                df.loc[idx, 'Female_closed'] = 1

    known_open_female = ['Askham Grange', 'East Sutton Park']
    known_closed_female = ['Bronzefield', 'Drake Hall', 'Downview', 'Eastwood Park', 
                           'Foston Hall', 'Holloway', 'Low Newton', 'New Hall', 
                           'Send', 'Styal']
    
    for idx, row in df.iterrows():
        if row['Prison_name'] in known_open_female:
            df.loc[idx, 'Female_open'] = 1
            df.loc[idx, 'Female_closed'] = 0
        elif row['Prison_name'] in known_closed_female:
            df.loc[idx, 'Female_open'] = 0
            df.loc[idx, 'Female_closed'] = 1
    
    # 5. Handle mixed prisons like Peterborough
    for idx, row in df.iterrows():
        if row['Mixed'] == 1 and row['Prison_name'] == 'Peterborough (Male & Female)':
            df.loc[idx, 'Female_closed'] = 1
    
    # 6. Ensure multi-category sites are correctly marked
    dual_security_sites = {
        'Grendon / Springhill': {'B': 1, 'D': 1, 'Notes': 'Grendon = Category B (therapeutic community), Springhill = Category D (open)'},
        'Moorland / Hatfield': {'C': 1, 'D': 1, 'Notes': 'Moorland = Category C, Hatfield = Category D (open)'},
        'Usk / Prescoed': {'C': 1, 'D': 1, 'Notes': 'Usk = Category C, Prescoed = Category D (open)'}
    }

    adult_yoi_sites = {
        'Littlehey': {'C': 1, 'YOI': 1, 'Notes': 'Adult side = Cat C, YOI side (18-21)'},
        'Rochester': {'C': 1, 'YOI': 1, 'Notes': 'Adult side = Cat C, YOI side (18-21)'},
        'Portland': {'C': 1, 'YOI': 1, 'Notes': 'Primarily Cat C adult, YOI/young adults side'},
        'Parc': {'B': 1, 'YOI': 1, 'Notes': 'Mainly Cat B local/training, has a separate YOI/juvenile unit (run by G4S)'},
        'Isis': {'C': 1, 'YOI': 1, 'Notes': 'Officially a Cat C prison, also designated as a YOI for 18-21 (London area)'},
        'Hindley': {'C': 1, 'YOI': 1, 'Notes': 'Re-rolled to Cat C for adult men, still holds some YOs/young adults'}
    }

    for prison, values in {**dual_security_sites, **adult_yoi_sites}.items():
        indices = df[df['Prison_name'] == prison].index
        for idx in indices:
            for key, value in values.items():
                df.loc[idx, key] = value

    # 7. Move Notes column to the end
    if 'Notes' in df.columns:
        notes_col = df.pop('Notes')
        df['Notes'] = notes_col

    return df



def add_highest_category_columns(prison_df):
    """
    Add columns for the highest security category for male and female prisoners.
    
    For males, the priority order is: A > B > C > D > YOI > Other
    For females, the priority order is: Closed > Open > Other
    
    Args:
        prison_df: The existing dataframe with prison data
        
    Returns:
        Updated dataframe with the new columns
    """
    # Make a copy to avoid modifying the original
    df = prison_df.copy()
    
    # Initialize the new columns with "Other"
    df['Highest_category_male'] = "Other"
    df['Highest_category_female'] = "Other"
    
    # Set highest category for male prisons according to priority
    for idx, row in df.iterrows():
        if row['Male'] == 1 or row['Mixed'] == 1:
            if row['A'] == 1:
                df.loc[idx, 'Highest_category_male'] = "A"
            elif row['B'] == 1:
                df.loc[idx, 'Highest_category_male'] = "B"
            elif row['C'] == 1:
                df.loc[idx, 'Highest_category_male'] = "C"
            elif row['D'] == 1:
                df.loc[idx, 'Highest_category_male'] = "D"
            elif row['YOI'] == 1:
                df.loc[idx, 'Highest_category_male'] = "YOI"
    
    # Set highest category for female prisons according to priority
    for idx, row in df.iterrows():
        if row['Female'] == 1 or row['Mixed'] == 1:
            if row['Female_closed'] == 1:
                df.loc[idx, 'Highest_category_female'] = "Closed"
            elif row['Female_open'] == 1:
                df.loc[idx, 'Highest_category_female'] = "Open"
    
    return df