import pandas as pd
import os
import re
import io
import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

# For RTF files
from striprtf.striprtf import rtf_to_text

# For PDF files
import pdfplumber
import traceback

from functions.file_scraping_functions import (
    save_to_csv,
    extract_report_date_from_file,
    extract_data_from_ods,
    extract_data_from_rtf,
    extract_data_from_pdf,
    extract_data_from_docx,
    extract_data_from_doc
)

def process_prison_file(file_path: str) -> pd.DataFrame:
    """
    Process a single prison statistics file
    
    Args:
        file_path: Path to the file
        
    Returns:
        DataFrame with processed data
    """
    try:
        # Extract the basic data
        df = extract_prison_data(file_path)
        
        if df is None or df.empty:
            print(f"No data extracted from {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        # Make sure we have a Report_Date column
        if 'Report_Date' not in df.columns:
            report_date = extract_report_date_from_file(file_path)
            if report_date:
                df['Report_Date'] = report_date
            else:
                print(f"Warning: Couldn't determine report date for {os.path.basename(file_path)}. Using file modification time as fallback.")
                # Use file modification time as fallback
                mtime = os.path.getmtime(file_path)
                df['Report_Date'] = datetime.datetime.fromtimestamp(mtime).date()
        
        # Find the row with "Total" or "Sub total" - this often indicates the end of the prison data
        if 'Prison Name' in df.columns:
            # Ensure Prison Name is a string column
            df['Prison Name'] = df['Prison Name'].astype(str)
            total_rows = df[df['Prison Name'].str.contains('total', case=False, na=False)].index.tolist()
            
            if total_rows:
                # Use the first occurrence of 'total' as cutoff
                total_row_idx = total_rows[0]
                print(f"Total row found at index: {total_row_idx}")
                
                # Exclude the total row and anything after it
                df = df.iloc[:total_row_idx].copy()
        
        # Standardize column names
        if 'Population' in df.columns and 'Population *' not in df.columns:
            df.rename(columns={'Population': 'Population *'}, inplace=True)
        
        # Convert numeric columns to float
        numeric_cols = ['Baseline CNA', 'In Use CNA', 'Operational Capacity', 'Population *']
        for col in numeric_cols:
            if col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace(',', '').str.replace(' ', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Ensure Report_Date is datetime
        if 'Report_Date' in df.columns:
            df['Report_Date'] = pd.to_datetime(df['Report_Date'], errors='coerce')
        
        # Save the extracted data to CSV
        save_to_csv(df, file_path)
        
        return df
    
    except Exception as e:
        print(f"Error processing {os.path.basename(file_path)}: {str(e)}")
        traceback.print_exc()
        return pd.DataFrame()
    

def extract_prison_data(file_path: str) -> pd.DataFrame:
    """
    Extract prison data from a file regardless of format (ODS, RTF, PDF, DOC, DOCX)
    
    Args:
        file_path: Path to the file
        
    Returns:
        DataFrame with prison data
    """
    try:
        # Determine file type from extension
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension == '.ods':
            return extract_data_from_ods(file_path)
        elif file_extension == '.rtf':
            return extract_data_from_rtf(file_path)
        elif file_extension == '.pdf':
            return extract_data_from_pdf(file_path)
        elif file_extension == '.docx':
            return extract_data_from_docx(file_path)
        elif file_extension == '.doc':
            return extract_data_from_doc(file_path)
        else:
            print(f"Unsupported file format: {file_extension}")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error in extract_prison_data for {os.path.basename(file_path)}: {str(e)}")
        traceback.print_exc()
        return pd.DataFrame()
    


def combine_prison_data(directory_path: str) -> pd.DataFrame:
    """
    Combine all prison statistics files in the directory
    
    Args:
        directory_path: Path to the directory containing prison data files
        
    Returns:
        Combined DataFrame with data from all files
    """
    try:
        # Convert to Path object
        directory = Path(directory_path)
        
        # Create Output directory if it doesn't exist
        output_dir = Path("Output/Monthly_reports_processed")
        output_dir.mkdir(exist_ok=True)
        
        # Find all relevant files (.ods, .rtf, .pdf, .doc, .docx in any case)
        files = []
        for ext in ['.ods', '.rtf', '.pdf', '.doc', '.docx']:
            files.extend(list(directory.glob(f'*{ext}')) + list(directory.glob(f'*{ext.upper()}')))
        
        # Also look in subdirectories for files
        for subdir in directory.glob('**/'):
            if subdir != directory:  # Skip the main directory which we already processed
                for ext in ['.ods', '.rtf', '.pdf', '.doc', '.docx']:
                    files.extend(list(subdir.glob(f'*{ext}')) + list(subdir.glob(f'*{ext.upper()}')))
        
        print(f"Found {len(files)} files to process")
        
        dfs = []
        processed_files = set()  # Track processed files to avoid duplicates
        all_columns = set()  # Keep track of all columns across DataFrames
        
        for file_path in files:
            try:
                # Skip if already processed (may happen if file exists in multiple places)
                if str(file_path) in processed_files:
                    continue
                    
                processed_files.add(str(file_path))
                
                # Use appropriate extraction method based on file type
                if file_path.suffix.lower() == '.ods':
                    df = extract_data_from_ods(str(file_path), str(output_dir))
                elif file_path.suffix.lower() == '.rtf':
                    df = extract_data_from_rtf(str(file_path), str(output_dir))
                elif file_path.suffix.lower() == '.pdf':
                    df = extract_data_from_pdf(str(file_path), str(output_dir))
                elif file_path.suffix.lower() == '.docx':
                    df = extract_data_from_docx(str(file_path), str(output_dir))
                elif file_path.suffix.lower() == '.doc':
                    df = extract_data_from_doc(str(file_path), str(output_dir))
                else:
                    print(f"Skipping unsupported file format: {file_path.name}")
                    continue
                
                # Check if this looks like a valid prison data file (should have Prison Name column)
                if df is None or df.empty or 'Prison Name' not in df.columns:
                    print(f"Skipping {file_path.name} - doesn't appear to contain valid prison data")
                    continue
                    
                # Make sure we have a Report_Date column
                if 'Report_Date' not in df.columns:
                    report_date = extract_report_date_from_file(str(file_path))
                    if report_date:
                        df['Report_Date'] = report_date
                    else:
                        print(f"Warning: Couldn't determine report date for {file_path.name}. Using file modification time as fallback.")
                        # Use file modification time as fallback
                        mtime = file_path.stat().st_mtime
                        df['Report_Date'] = datetime.datetime.fromtimestamp(mtime).date()
                
                # Print debug info about date extraction
                month_year_match = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)[_-]?(\d{4})', file_path.name.lower(), re.IGNORECASE)
                if month_year_match:
                    print(month_year_match)
                
                if df is not None and not df.empty:
                    # Update all_columns set with columns from this DataFrame
                    all_columns.update(df.columns)
                    print(f"Successfully processed {file_path.name} - {len(df)} rows")
                    dfs.append(df)
                else:
                    print(f"No data extracted from {file_path.name}")
            except Exception as e:
                print(f"Failed to process {file_path.name}: {str(e)}")
                traceback.print_exc()
        
        if not dfs:
            raise ValueError("No valid data found in any of the files")
        
        # Define columns to remove
        columns_to_remove = ["% Pop to In Use CNA", "% Accommodation Available"]
        
        # Create a list of all unique columns, excluding unwanted ones
        standard_columns = [col for col in all_columns if col not in columns_to_remove]
        
        # Standardize DataFrames to have same structure
        standardized_dfs = []
        for df in dfs:
            # Remove unwanted columns if they exist
            df = df.drop(columns=[col for col in columns_to_remove if col in df.columns])
            
            # Add missing columns with NaN values
            for col in standard_columns:
                if col not in df.columns:
                    df[col] = pd.NA
            
            # Keep only relevant columns
            df = df[standard_columns]
            standardized_dfs.append(df)
        
        # Combine all standardized dataframes
        combined_df = pd.concat(standardized_dfs, ignore_index=True)
        
        # Standardize column names
        if 'Population' in combined_df.columns and 'Population *' not in combined_df.columns:
            combined_df.rename(columns={'Population': 'Population *'}, inplace=True)
        
        # Ensure all columns are the right type
        # Convert numeric columns to float
        numeric_cols = ['Baseline CNA', 'In Use CNA', 'Operational Capacity', 'Population *']
        for col in numeric_cols:
            if col in combined_df.columns:
                combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')
        
        # Ensure Report_Date is datetime
        if 'Report_Date' in combined_df.columns:
            combined_df['Report_Date'] = pd.to_datetime(combined_df['Report_Date'], errors='coerce')
        
        # Sort by date and prison name
        if 'Report_Date' in combined_df.columns:
            combined_df = combined_df.sort_values(['Report_Date', 'Prison Name'])
        else:
            combined_df = combined_df.sort_values('Prison Name')
        
        # Remove duplicate rows
        combined_df = combined_df.drop_duplicates()
        
        # Save the combined dataset to CSV
        combined_output_path = output_dir / "combined_prison_data.csv"
        combined_df.to_csv(combined_output_path, index=False)
        print(f"Saved combined data from {len(dfs)} files to {combined_output_path}")
        
        return combined_df
        
    except Exception as e:
        print(f"Critical error in combine_prison_data: {str(e)}")
        traceback.print_exc()
        raise


def create_prison_time_series(csv_path: str, exclude_months: Optional[Union[str, List[str]]] = None) -> pd.DataFrame:
    """
    Create time series of prison capacity metrics by reading the combined CSV file,
    grouping by month, and summing metrics across all prisons.
    
    Args:
        csv_path: Path to the combined prison data CSV file
        exclude_months: Optional; A single year-month string (e.g., '2023-01') or a list of 
                        year-month strings to exclude from the final time series
        
    Returns:
        DataFrame with monthly time series data for key metrics
    """
    # List of columns to include in the time series
    metrics = ['Baseline CNA', 'In Use CNA', 'Operational Capacity', 'Population *']
    
    # Create an empty DataFrame to store the results
    monthly_data = pd.DataFrame()
    
    # Read the CSV in chunks to handle large file size efficiently
    chunk_size = 10000  # Adjust based on file size and available memory
    
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        # Convert Report_Date to datetime
        chunk['Report_Date'] = pd.to_datetime(chunk['Report_Date'])
        
        # Extract year-month from Report_Date
        chunk['Year_Month'] = chunk['Report_Date'].dt.to_period('M')
        
        # Remove rows with any missing metrics
        chunk = chunk.dropna(subset=metrics)
        
        # Group by year-month and sum the metrics
        monthly_chunk = chunk.groupby('Year_Month')[metrics].sum().reset_index()
        
        # Append to the results DataFrame
        monthly_data = pd.concat([monthly_data, monthly_chunk], ignore_index=True)
    
    # Reaggregate in case multiple chunks had the same months
    monthly_data = monthly_data.groupby('Year_Month')[metrics].sum().reset_index()
    
    # Sort by date
    monthly_data = monthly_data.sort_values('Year_Month')
    
    # Convert Year_Month to string for better readability
    monthly_data['Year_Month'] = monthly_data['Year_Month'].astype(str)
    
    # Filter out excluded months if specified
    if exclude_months is not None:
        # Convert single string to list for consistent processing
        if isinstance(exclude_months, str):
            exclude_months = [exclude_months]
        
        # Filter out the specified months
        monthly_data = monthly_data[~monthly_data['Year_Month'].isin(exclude_months)]
        
        print(f"Excluded {len(exclude_months)} month(s) from the time series")
    
    return monthly_data


def analyze_prison_capacity(df: pd.DataFrame) -> Dict[str, Union[float, List[str]]]:
    """
    Analyze prison capacity data
    
    Args:
        df: DataFrame with prison data
        
    Returns:
        Dictionary with analysis results
    """
    # Filter out non-prison rows (totals, headers, etc.)
    prison_df = df[~df['Prison Name'].str.contains('total|Total|IRC', regex=True, na=False)]
    
    # Calculate occupancy rate directly - we no longer rely on "% Pop to In Use CNA" column
    prison_df = prison_df.copy()
    prison_df['occupancy_rate'] = (prison_df['Population *'] / prison_df['In Use CNA'] * 100)
    
    # Calculate overall statistics
    avg_occupancy = prison_df['occupancy_rate'].mean()
    
    overcrowded_prisons = prison_df[prison_df['Population *'] > prison_df['Operational Capacity']]['Prison Name'].tolist()
    
    if not prison_df.empty and 'Population *' in prison_df.columns and 'In Use CNA' in prison_df.columns:
        # Find most overcrowded prison using the calculated occupancy rate
        most_overcrowded_idx = prison_df['occupancy_rate'].idxmax()
        most_overcrowded = prison_df.loc[most_overcrowded_idx]
    else:
        most_overcrowded = pd.Series({'Prison Name': 'Unknown', 'occupancy_rate': 0})
    
    return {
        'average_occupancy_percent': avg_occupancy,
        'overcrowded_prisons_count': len(overcrowded_prisons),
        'overcrowded_prisons': overcrowded_prisons,
        'most_overcrowded_prison': most_overcrowded['Prison Name'],
        'most_overcrowded_percent': most_overcrowded['occupancy_rate']
    }


def standardize_death_types(df, column_name='type_of_death'):
    """
    Standardize death type categories in a pandas DataFrame.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        The DataFrame containing the death type data.
    column_name : str, default='type_of_death'
        The name of the column to standardize.
        
    Returns:
    --------
    pandas.DataFrame
        A copy of the input DataFrame with standardized death types.
    """
    # Create a copy to avoid modifying the original DataFrame
    df_copy = df.copy()
    
    # Convert all values to lowercase first
    df_copy[column_name] = df_copy[column_name].str.lower()
    
    # Create mapping dictionary for standardization
    mapping = {
        'natural causes': 'Natural Causes',
        'self-inflicted': 'Self-Inflicted',
        'self inflicted': 'Self-Inflicted',  # In case there are variations without hyphen
        'homicide': 'Homicide'
    }
    
    # Apply the specific mappings first
    df_copy[column_name] = df_copy[column_name].replace(mapping)
    
    # Replace all categories starting with "other:" with just "Other"
    df_copy[column_name] = df_copy[column_name].apply(
        lambda x: 'Other' if x.startswith('other:') else x
    )
    
    return df_copy



# Create a function to calculate death rates for each age group, year, and cause
def calculate_age_specific_rates(deaths_df, population_df):
    # Create an empty DataFrame to store results
    results = []
    
    # For each year in the population data
    for _, pop_row in population_df.iterrows():
        year = pop_row['Year_numeric'] if 'Year_numeric' in pop_row else int(pop_row['Year'])
        
        # Get deaths for this year
        year_deaths = deaths_df[deaths_df['year'] == year]
        
        # For each age category and cause of death
        for age_cat in ['Age_15_20', 'Age_21_29', 'Age_30_39', 'Age_40_49', 'Age_50+']:
            # Get population for this age category
            population = pop_row[age_cat]
            
            # Extract deaths for this age category
            age_deaths = year_deaths[year_deaths['age_category'] == age_cat]
            
            # For each cause of death
            for cause in ['Natural Causes', 'Self-Inflicted', 'Other', 'Homicide']:
                # Get deaths for this cause
                cause_deaths = age_deaths[age_deaths['type_of_death'] == cause]
                
                # Calculate total deaths for this combination
                total = cause_deaths['total_deaths'].sum() if not cause_deaths.empty else 0
                
                # Calculate rate per 1000 prisoners
                rate = (total / population) * 1000 if population > 0 else 0
                
                # Add to results
                results.append({
                    'year': year,
                    'age_category': age_cat,
                    'cause_of_death': cause,
                    'deaths': total,
                    'population': population,
                    'rate_per_1000': rate
                })
    
    # Convert to DataFrame
    return pd.DataFrame(results)