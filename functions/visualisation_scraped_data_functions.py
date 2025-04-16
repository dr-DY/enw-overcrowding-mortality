import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import os

def create_visualizations(df, output_dir):
    """Create and save visualizations of the time series data"""
    # Set the style
    sns.set(style="whitegrid")
    plt.figure(figsize=(12, 8))
    
    # Create a plot for all metrics
    metrics = ['Baseline CNA', 'In Use CNA', 'Operational Capacity', 'Population *']
    
    # Convert Year_Month from string back to datetime for proper plotting
    df['Year_Month'] = pd.to_datetime(df['Year_Month'])
    
    # Plot each metric
    for metric in metrics:
        plt.plot(df['Year_Month'], df[metric], marker='o', linestyle='-', label=metric)
    
    # Add labels and legend
    plt.title('Prison Capacity Metrics Over Time', fontsize=16)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Number of Places/Prisoners', fontsize=12)
    plt.legend(loc='best')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save the figure
    output_file = output_dir / "prison_capacity_time_series.png"
    plt.savefig(output_file, dpi=300)
    print(f"Saved visualization to {output_file}")
    
    # Create a second visualization showing occupancy rate
    plt.figure(figsize=(12, 8))
    
    # Calculate occupancy rate (Population / In Use CNA)
    df['Occupancy Rate'] = (df['Population *'] / df['In Use CNA'] * 100)
    
    # Plot occupancy rate
    plt.plot(df['Year_Month'], df['Occupancy Rate'], marker='o', linestyle='-', color='crimson')
    
    # Add a horizontal line at 100% (full capacity)
    plt.axhline(y=100, color='black', linestyle='--', alpha=0.7)
    
    # Add labels
    plt.title('Prison Occupancy Rate Over Time', fontsize=16)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Occupancy Rate (%)', fontsize=12)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save the figure
    output_file = output_dir / "prison_occupancy_rate.png"
    plt.savefig(output_file, dpi=300)
    print(f"Saved occupancy rate visualization to {output_file}")