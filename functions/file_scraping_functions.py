import pandas as pd
import os
import re
import io
import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

# For RTF files
from striprtf.striprtf import rtf_to_text

# For DOCX files - make it globally available as None if not installed
docx = None
try:
    import python_docx
    docx = python_docx
except ImportError:
    try:
        import docx
    except ImportError:
        print("Warning: python-docx package not installed. DOCX file processing will not be available.")
        print("Install with: pip install python-docx")

# For DOC files - platform-specific approaches without textract
import platform
import subprocess
try:
    # For Windows
    if platform.system() == 'Windows':
        try:
            import win32com.client
        except ImportError:
            print("Warning: pywin32 not installed. DOC file processing may be limited on Windows.")
            print("Install with: pip install pywin32")
except Exception as e:
    print(f"Error importing win32com: {str(e)}")

# For PDF files
import pdfplumber
import traceback

def docx_to_text(file_path: str) -> str:
    """
    Convert DOCX file to plain text.
    
    Args:
        file_path: Path to the DOCX file
        
    Returns:
        Plain text content of the DOCX file
    """
    global docx
    
    # First check if docx module is available
    if docx is None:
        try:
            import python_docx
            docx = python_docx
        except ImportError:
            try:
                import docx
            except ImportError:
                print("Error: python-docx package not installed. Cannot process DOCX files.")
                print("Install with: pip install python-docx")
                return ""
    
    try:
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        print(f"Error converting DOCX to text: {str(e)}")
        traceback.print_exc()
        
        # Fallback to simple file extraction if docx parsing fails
        try:
            import zipfile
            from xml.etree.ElementTree import XML
            
            # Define DOCX MIME mapping for document.xml
            WORD_NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            PARA = WORD_NAMESPACE + 'p'
            TEXT = WORD_NAMESPACE + 't'
            
            # Extract content from document.xml in DOCX file (which is a ZIP file)
            with zipfile.ZipFile(file_path) as zip_file:
                try:
                    xml_content = zip_file.read('word/document.xml')
                    tree = XML(xml_content)
                    
                    paragraphs = []
                    for paragraph in tree.iterfind('.//' + PARA):
                        texts = [node.text for node in paragraph.iterfind('.//' + TEXT) if node.text]
                        if texts:
                            paragraphs.append(''.join(texts))
                            
                    return '\n'.join(paragraphs)
                except Exception as zip_error:
                    print(f"Fallback DOCX extraction also failed: {str(zip_error)}")
        except Exception as fallback_error:
            print(f"All DOCX extraction methods failed: {str(fallback_error)}")
            
        return ""


def convert_doc_to_docx(doc_path: str) -> str:
    """
    Convert a DOC file to DOCX format using Microsoft Word automation.
    
    Args:
        doc_path: Path to the DOC file
        
    Returns:
        Path to the converted DOCX file, or empty string if conversion failed
    """
    if not doc_path.lower().endswith('.doc'):
        return ""
        
    # Create output path for the DOCX file
    docx_path = os.path.splitext(doc_path)[0] + '_converted.docx'
    
    # Skip if already converted
    if os.path.exists(docx_path):
        return docx_path
        
    # Check if this is a temp/backup file (starts with ~$)
    is_temp_file = os.path.basename(doc_path).startswith('~$')
    
    try:
        # Only attempt conversion on Windows
        if platform.system() != 'Windows':
            print(f"DOC to DOCX conversion requires Windows. Skipping {os.path.basename(doc_path)}")
            return ""
            
        # Use Word automation to convert
        import win32com.client
        
        # Create Word application instance
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        
        try:
            # Get absolute paths
            abs_doc_path = os.path.abspath(doc_path)
            abs_docx_path = os.path.abspath(docx_path)
            
            # Handle temp/backup files
            if is_temp_file:
                print(f"Processing temporary Word file: {os.path.basename(doc_path)}")
                
                # For temporary files, try to find and use the original file if possible
                original_name = os.path.basename(doc_path)[2:]  # Remove ~$ prefix
                dir_path = os.path.dirname(doc_path)
                original_path = os.path.join(dir_path, original_name)
                
                if os.path.exists(original_path):
                    print(f"Found original file: {original_name}. Using it instead of the temp file.")
                    abs_doc_path = os.path.abspath(original_path)
            
            # Open the document
            doc = word.Documents.Open(abs_doc_path)
            
            # Save as DOCX
            doc.SaveAs2(abs_docx_path, FileFormat=16)  # 16 = DOCX format
            
            # Close the document
            doc.Close(SaveChanges=False)
            
            print(f"Successfully converted {os.path.basename(abs_doc_path)} to DOCX format")
            return docx_path
            
        except Exception as e:
            print(f"Error converting DOC to DOCX: {str(e)}")
            traceback.print_exc()
            return ""
        finally:
            # Ensure Word is closed even if conversion fails
            try:
                word.Quit()
            except:
                pass
    except Exception as e:
        print(f"Error during DOC to DOCX conversion: {str(e)}")
        return ""


def doc_to_text(file_path: str) -> str:
    """
    Convert DOC file to plain text using platform-specific methods.
    
    Args:
        file_path: Path to the DOC file
        
    Returns:
        Plain text content of the DOC file
    """
    system = platform.system()
    text = ""
    
    # Check if this is a temp/backup file (starts with ~$)
    is_temp_file = os.path.basename(file_path).startswith('~$')
    
    try:
        if system == 'Windows':
            # Try Windows-specific approach with win32com
            try:
                import win32com.client
                
                # Create Word application instance
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                word.DisplayAlerts = False
                
                try:
                    # Get absolute path
                    abs_path = os.path.abspath(file_path)
                    
                    # For temporary files, try to find and use the original file if possible
                    if is_temp_file:
                        original_name = os.path.basename(file_path)[2:]  # Remove ~$ prefix
                        dir_path = os.path.dirname(file_path)
                        original_path = os.path.join(dir_path, original_name)
                        
                        if os.path.exists(original_path):
                            print(f"Using original file: {original_name} instead of temp file.")
                            abs_path = os.path.abspath(original_path)
                    
                    # Open the document
                    doc = word.Documents.Open(abs_path)
                    
                    # Extract all text
                    for para in doc.Paragraphs:
                        text += para.Range.Text + "\n"
                        
                    # Alternative method if the above doesn't work
                    if not text:
                        for i in range(doc.Paragraphs.Count):
                            text += doc.Paragraphs(i+1).Range.Text + "\n"
                    
                    # Close the document and word
                    doc.Close(SaveChanges=False)
                    
                    # Validate the extracted text
                    if text and is_valid_doc_text(text):
                        return text
                    else:
                        print(f"Warning: Text extracted via Word automation appears corrupted for {os.path.basename(file_path)}")
                except Exception as doc_ex:
                    print(f"Word document open/read error: {str(doc_ex)}")
                finally:
                    # Ensure Word is closed even if extraction fails
                    try:
                        word.Quit()
                    except:
                        pass
            except Exception as e:
                print(f"Error using win32com to read DOC file: {str(e)}")
        
        # Try direct OLE file reading (works with both Windows and non-Windows)
        try:
            import olefile
            if olefile.isOleFile(file_path):
                ole = olefile.OleFileIO(file_path)
                
                # Attempt to extract text from the WordDocument stream
                if ole.exists('WordDocument'):
                    word_data = ole.openstream('WordDocument').read()
                    text_parts = []
                    
                    # Extract ASCII text - simple approach
                    text = ''.join(chr(b) for b in word_data if 32 <= b < 127 or b in (10, 13))
                    
                    # Clean up text and check if it's valid
                    text = re.sub(r'[^\x20-\x7E\n\r]', '', text)
                    text = re.sub(r'\s+', ' ', text)
                    
                    # If we found text and it has some meaningful content
                    if text and len(text) > 100 and is_valid_doc_text(text):
                        return text
        except ImportError:
            print("olefile not available - cannot extract DOC file content directly")
            print("Install with: pip install olefile")
        except Exception as ole_error:
            print(f"Error using olefile to read DOC file: {str(ole_error)}")
        
        # Try using antiword if available (Linux/Unix)
        try:
            # Check if antiword is installed
            if system == 'Windows':
                antiword_check = subprocess.run(['where', 'antiword'], 
                                             stdout=subprocess.PIPE, 
                                             stderr=subprocess.PIPE, 
                                             text=True,
                                             check=False)
            else:
                antiword_check = subprocess.run(['which', 'antiword'], 
                                             stdout=subprocess.PIPE, 
                                             stderr=subprocess.PIPE, 
                                             text=True,
                                             check=False)
            
            if antiword_check.returncode == 0:  # antiword is available
                result = subprocess.run(['antiword', file_path], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE, 
                                       text=True,
                                       check=False)
                if result.returncode == 0 and result.stdout:
                    text = result.stdout
                    if is_valid_doc_text(text):
                        return text
                    else:
                        print(f"Warning: Text extracted via antiword appears corrupted for {os.path.basename(file_path)}")
        except Exception as e:
            print(f"Error using antiword to read DOC file: {str(e)}")
            
        # Try catdoc if available (another option for Unix/Linux)
        try:
            # Check if catdoc is installed
            if system == 'Windows':
                catdoc_check = subprocess.run(['where', 'catdoc'], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE, 
                                           text=True,
                                           check=False)
            else:
                catdoc_check = subprocess.run(['which', 'catdoc'], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE, 
                                           text=True,
                                           check=False)
            
            if catdoc_check.returncode == 0:  # catdoc is available
                result = subprocess.run(['catdoc', file_path], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE, 
                                       text=True,
                                       check=False)
                if result.returncode == 0 and result.stdout:
                    text = result.stdout
                    if is_valid_doc_text(text):
                        return text
                    else:
                        print(f"Warning: Text extracted via catdoc appears corrupted for {os.path.basename(file_path)}")
        except Exception as e:
            print(f"Error using catdoc to read DOC file: {str(e)}")
        
        # Try converting to DOCX and then extract text
        if system == 'Windows':
            try:
                print(f"Attempting to convert DOC to DOCX as a fallback for {os.path.basename(file_path)}")
                docx_path = convert_doc_to_docx(file_path)
                if docx_path and os.path.exists(docx_path):
                    # Extract text from the converted DOCX file
                    converted_text = docx_to_text(docx_path)
                    if converted_text and is_valid_doc_text(converted_text):
                        print(f"Successfully extracted text from converted DOCX: {os.path.basename(docx_path)}")
                        return converted_text
            except Exception as convert_error:
                print(f"Error converting DOC to DOCX: {str(convert_error)}")
        
        # Last resort: attempt to extract some text using binary analysis
        try:
            # Read file in binary mode
            with open(file_path, 'rb') as doc_file:
                content = doc_file.read()
                
            # Try to extract chunks of text
            # This regex looks for sequences that look like text
            text_chunks = re.findall(b'[\x20-\x7E\n\r]{4,}', content)
            if text_chunks:
                text = b'\n'.join(text_chunks).decode('utf-8', errors='ignore')
                
                # Clean up extracted text
                text = re.sub(r'[^\x20-\x7E\n\r]', '', text)
                text = re.sub(r'\s+', ' ', text)
                
                # Check if the text contains keywords typically found in prison data
                prison_keywords = ['Prison', 'CNA', 'Capacity', 'Population']
                if any(keyword in text for keyword in prison_keywords):
                    return text
        except Exception as fallback_error:
            print(f"Last-resort text extraction failed: {str(fallback_error)}")
            
        print(f"Warning: Unable to extract valid text from DOC file {os.path.basename(file_path)}. "
              f"Consider converting it to DOCX format or installing better DOC processing tools.")
        return ""
    except Exception as e:
        print(f"Error converting DOC to text: {str(e)}")
        traceback.print_exc()
        return ""


def is_valid_doc_text(text: str) -> bool:
    """
    Validate if the extracted text from a DOC file is likely to be valid.
    
    Args:
        text: Extracted text to validate
        
    Returns:
        Boolean indicating if the text appears valid
    """
    if not text or len(text) < 100:
        return False
    
    # Check if text contains too many non-ASCII or control characters
    non_ascii_count = sum(1 for char in text if ord(char) > 127 or (ord(char) < 32 and char not in '\n\t\r'))
    if non_ascii_count / len(text) > 0.20:  # More than 20% strange characters - increased threshold
        return False
    
    # Check for common signs of binary data or encoding corruption
    suspicious_patterns = [
        '@Unknown',
        'Times N',
        '\x00',
        '}\x00{'
    ]
    
    # For Microsoft Word and Office, only check if they appear multiple times
    # or not in a context that suggests real text
    ms_patterns = ['Microsoft Word', 'Microsoft Office']
    ms_pattern_count = sum(text.count(pattern) for pattern in ms_patterns)
    
    if ms_pattern_count > 3 or any(pattern in text for pattern in suspicious_patterns):
        return False
    
    # Check if text contains some relevant keywords we expect in prison data files
    prison_keywords = [
        'Prison',
        'CNA',
        'Capacity',
        'Population',
        'Report Date',
        'Operational'
    ]
    
    # Must contain at least one expected keyword
    if not any(keyword in text for keyword in prison_keywords):
        
        # Special case: check for data-like patterns
        # Looking for lines with a mixture of text and numbers
        lines = text.split('\n')
        data_like_pattern = re.compile(r'^[A-Za-z][A-Za-z\s]+\s+\d+\s+\d+')
        data_like_lines = [line for line in lines if data_like_pattern.match(line)]
        
        if len(data_like_lines) < 5:  # Need at least a few rows of data
            return False
        
    return True


def save_to_csv(df: pd.DataFrame, original_file_path: str, output_dir_path: str) -> None:
    """
    Save dataframe to CSV in the Output directory with the same name as the original file
    
    Args:
        df: DataFrame to save
        original_file_path: Path to the original file
    """
    if df is None or df.empty:
        return
        
    # Create Output directory if it doesn't exist
    output_dir = Path(output_dir_path)
    output_dir.mkdir(exist_ok=True)
    
    # Get original filename without extension
    original_filename = Path(original_file_path).stem
    
    # Create new path with .csv extension
    output_path = output_dir / f"{original_filename}.csv"
    
    # Save to CSV
    try:
        df.to_csv(output_path, index=False)
        print(f"Saved extracted data to {output_path}")
    except Exception as e:
        print(f"Error saving to CSV: {str(e)}")
        traceback.print_exc()


def extract_report_date_from_file(file_path: str) -> Optional[datetime.date]:
    """
    Extract the report date from a prison data file
    
    Args:
        file_path: Path to the file
        
    Returns:
        Report date as a datetime.date object if found, None otherwise
    """
    file_extension = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path).lower()
    
    # First check for date in the file content
    if file_extension == '.rtf':
        # Read and convert RTF to plain text
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            rtf_content = file.read()
        text = rtf_to_text(rtf_content)
        
        # Look for the report date pattern in RTF files
        date_pattern = r'Report Date:\s*(\d{2}/\d{2}/\d{4})'
        match = re.search(date_pattern, text)
        if match:
            date_str = match.group(1)
            try:
                return datetime.datetime.strptime(date_str, '%d/%m/%Y').date()
            except ValueError:
                pass
                
    elif file_extension == '.pdf':
        with pdfplumber.open(file_path) as pdf:
            # Check the first page for the date
            if len(pdf.pages) > 0:
                text = pdf.pages[0].extract_text()
                date_pattern = r'Report Date:\s*(\d{2}/\d{2}/\d{4})'
                match = re.search(date_pattern, text)
                if match:
                    date_str = match.group(1)
                    try:
                        return datetime.datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        pass
    
    elif file_extension == '.docx':
        try:
            text = docx_to_text(file_path)
            date_pattern = r'Report Date:\s*(\d{2}/\d{2}/\d{4})'
            match = re.search(date_pattern, text)
            if match:
                date_str = match.group(1)
                try:
                    return datetime.datetime.strptime(date_str, '%d/%m/%Y').date()
                except ValueError:
                    pass
        except Exception as e:
            print(f"Error extracting date from DOCX: {str(e)}")
            
    elif file_extension == '.doc':
        try:
            text = doc_to_text(file_path)
            date_pattern = r'Report Date:\s*(\d{2}/\d{2}/\d{4})'
            match = re.search(date_pattern, text)
            if match:
                date_str = match.group(1)
                try:
                    return datetime.datetime.strptime(date_str, '%d/%m/%Y').date()
                except ValueError:
                    pass
        except Exception as e:
            print(f"Error extracting date from DOC: {str(e)}")
    
    # Next, try to extract date from filename
    
    # Match month names with year patterns
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 
        'oct': 10, 'nov': 11, 'dec': 12
    }
    
    # Check for various filename patterns like:
    # - prison-pop-month-year.ods
    # - prison-pop-month_year.ods
    # - monthly-bulletin-month-year.ods
    # - Monthly_Bulletin_Month_Year_web.ODS
    # - Population_bulletin_monthly_Month_Year_Corrected.ods
    
    # Find year in the filename (4 digits)
    year_match = re.search(r'20\d{2}', filename)
    
    if year_match:
        year = int(year_match.group())
        
        # Find month in the filename
        for month_name, month_num in months.items():
            # Try different separators: hyphen, underscore
            for separator in ['-', '_']:
                # Search for patterns like "month-year" or "month_year"
                month_year_pattern = f"{month_name}{separator}?{year}"
                if re.search(month_year_pattern, filename):
                    # Set the default day to last day of month
                    last_day = 28 if month_num == 2 else 30 if month_num in [4, 6, 9, 11] else 31
                    return datetime.date(year, month_num, last_day)
                
                # Also search for "year-month" or "year_month" patterns
                year_month_pattern = f"{year}{separator}?{month_name}"
                if re.search(year_month_pattern, filename):
                    last_day = 28 if month_num == 2 else 30 if month_num in [4, 6, 9, 11] else 31
                    return datetime.date(year, month_num, last_day)
                
                # Look for month alone (when year is elsewhere in filename)
                if re.search(f"{separator}{month_name}{separator}", filename) or filename.startswith(f"{month_name}{separator}") or filename.endswith(f"{separator}{month_name}"):
                    last_day = 28 if month_num == 2 else 30 if month_num in [4, 6, 9, 11] else 31
                    return datetime.date(year, month_num, last_day)
    
    # If we can't find a date from the standard patterns, try alternative approaches
    
    # Pattern for monthly_bulletin files
    if "monthly" in filename and "bulletin" in filename:
        # Look for month and year in any order
        for month_name, month_num in months.items():
            if month_name in filename:
                year_match = re.search(r'20\d{2}', filename)
                if year_match:
                    year = int(year_match.group())
                    last_day = 28 if month_num == 2 else 30 if month_num in [4, 6, 9, 11] else 31
                    return datetime.date(year, month_num, last_day)
    
    # Pattern for prison-pop files
    if "prison-pop" in filename or "prison_pop" in filename:
        for month_name, month_num in months.items():
            if month_name in filename:
                year_match = re.search(r'20\d{2}', filename)
                if year_match:
                    year = int(year_match.group())
                    last_day = 28 if month_num == 2 else 30 if month_num in [4, 6, 9, 11] else 31
                    return datetime.date(year, month_num, last_day)
    
    # If we can't find a date, return None
    return None


def extract_data_from_ods(file_path: str, output_path: str) -> pd.DataFrame:
    """
    Extract prison data from ODS file
    
    Args:
        file_path: Path to the ODS file
        
    Returns:
        DataFrame with prison data
    """
    try:
        # Read the file with all rows as strings to better handle mixed data types
        df = pd.read_excel(file_path, engine='odf', header=None, dtype=str)
        
        # Find the header row
        header_row = None
        for idx, row in df.iterrows():
            if isinstance(row[0], str) and row[0].strip() == 'Prison Name':
                header_row = idx
                break
        
        if header_row is None:
            print(f"Warning: No header row found in {os.path.basename(file_path)}")
            return pd.DataFrame()
        
        # Set the headers and get data after header row
        headers = df.iloc[header_row]
        df = df.iloc[header_row + 1:].copy()
        df.columns = headers
        
        # Reset the index
        df = df.reset_index(drop=True)
        
        # Find the first occurrence of a row containing 'total' (case-insensitive)
        if 'Prison Name' in df.columns:
            # Convert to string to avoid errors with non-string values
            df['Prison Name'] = df['Prison Name'].astype(str)
            mask = df['Prison Name'].str.contains('total', case=False, na=False)
            if mask.any():  # Check if any row matches the condition
                total_row_idx = mask.idxmax()  # Get the index of the first match
                print(f"Total row found at index: {total_row_idx}")
                
                # Keep only the rows before the first occurrence
                df = df.iloc[:total_row_idx].copy()
        
        # Convert numeric columns
        numeric_columns = ['Baseline CNA', 'In Use CNA', 'Operational Capacity', 'Population *']
        for col in numeric_columns:
            if col in df.columns:
                # Remove commas, spaces in numeric values
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace(',', '').str.replace(' ', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Check for conversion issues
                if df[col].isna().sum() > 0:
                    print(f"Warning: {df[col].isna().sum()} values in {col} converted to NaN")
        
        # Extract date from the filename
        if isinstance(file_path, str):
            file_path = Path(file_path)
            
        # Extract report date (first try with extract_report_date_from_file for consistency)
        report_date = extract_report_date_from_file(file_path)
        if report_date:
            df['Report_Date'] = report_date
        else:
            # Fall back to your extract_date_from_filename approach with modified implementation
            filename = os.path.basename(file_path).lower()
            months = {
                'january': 1, 'jan': 1,
                'february': 2, 'feb': 2,
                'march': 3, 'mar': 3,
                'april': 4, 'apr': 4,
                'may': 5,
                'june': 6, 'jun': 6,
                'july': 7, 'jul': 7,
                'august': 8, 'aug': 8,
                'september': 9, 'sep': 9, 'sept': 9,
                'october': 10, 'oct': 10,
                'november': 11, 'nov': 11,
                'december': 12, 'dec': 12
            }
            
            # Use regex to find month and year in filename
            month_pattern = '|'.join(months.keys())
            match = re.search(rf'({month_pattern})[-_\s]*(\d{{4}})', filename)
            
            if match:
                print(match)
                month_name, year = match.groups()
                month_num = months[month_name]
                df['Report_Date'] = pd.to_datetime(f"{year}-{month_num:02d}-01")
            else:
                # Try the reverse pattern: year followed by month
                match = re.search(rf'(\d{{4}})[-_\s]*({month_pattern})', filename)
                if match:
                    print(match)
                    year, month_name = match.groups()
                    month_num = months[month_name]
                    df['Report_Date'] = pd.to_datetime(f"{year}-{month_num:02d}-01")
                else:
                    print(f"DEBUG: Could not extract date from filename: {filename}")
                    
                    # Last resort: check if year and any month name exist separately
                    year_match = re.search(r'20\d{2}', filename)
                    
                    for month_name, month_num in months.items():
                        if month_name in filename and year_match:
                            year = year_match.group()
                            df['Report_Date'] = pd.to_datetime(f"{year}-{month_num:02d}-01")
                            print(f"Using separate year and month: {year}-{month_num:02d}-01")
                            break
        
        # Verify required columns exist
        required_columns = ['Prison Name', 'Report_Date']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"Warning: Missing required columns in {os.path.basename(file_path)}: {missing_columns}")
            if 'Report_Date' in missing_columns:
                print(f"No report date could be extracted from {os.path.basename(file_path)}")
                return pd.DataFrame()
        
        # Select and reorder columns
        columns = ['Prison Name', 'Baseline CNA', 'In Use CNA', 'Operational Capacity', 
                  'Population *', 'Report_Date']
        
        # Only keep columns that exist in the DataFrame
        available_columns = [col for col in columns if col in df.columns]
        
        if available_columns:
            df = df[available_columns]
            
            # Remove any remaining rows with NaN values in important columns
            # Ensure 'Prison Name' exists before checking
            if 'Prison Name' in df.columns:
                df = df.dropna(subset=['Prison Name'])
            
            # For numeric columns that exist in the DataFrame
            available_numeric_columns = [col for col in numeric_columns if col in df.columns]
            if available_numeric_columns:
                # Don't drop rows that are missing some numeric data
                # Just drop rows where ALL numeric columns are NaN
                df = df.dropna(how='all', subset=available_numeric_columns)
        
        # Check if we have valid data
        if df.empty:
            print(f"Warning: No valid data extracted from {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        # Save the extracted data to CSV
        save_to_csv(df, file_path, output_path)
            
        return df
        
    except Exception as e:
        print(f"\nDetailed error in {os.path.basename(file_path)}:")
        traceback.print_exc()
        return pd.DataFrame()
    

def extract_data_from_rtf(file_path: str, output_path: str) -> pd.DataFrame:
    """
    Extract prison data from RTF file
    
    Args:
        file_path: Path to the RTF file
        
    Returns:
        DataFrame with prison data
    """
    try:
        # Read and convert RTF to plain text
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            rtf_content = file.read()
        
        text = rtf_to_text(rtf_content)
        
        # Process the text to extract tabular data
        # Split text into lines
        lines = text.split('\n')
        
        # Define column names based on the header in the RTF file
        column_names = None
        data = []
        in_data_section = False
        prison_data_started = False
        data_section_ended = False  # Flag to indicate end of data section
        
        # First pass: identify column headers and prepare for data extraction
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Find the header row that contains "Prison Name"
            if "Prison Name" in line and ("Baseline" in line or "CNA" in line):
                # We've found the header row
                header_line = line
                in_data_section = True
                
                # Look for continuation of header in next line if needed
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and "Capacity" in next_line and not re.match(r'^[A-Za-z]', next_line):
                        # This is likely a continuation of the header
                        header_line += " " + next_line
                
                # Extract column names from header
                # For multi-part headers, use a more flexible regex
                header_parts = re.split(r'\s{2,}', header_line)
                column_names = [part.strip() for part in header_parts if part.strip()]
                
                # Fix common column name issues
                if 'Operational' in column_names and 'Capacity' in column_names:
                    # These might be split due to formatting
                    op_idx = column_names.index('Operational')
                    cap_idx = column_names.index('Capacity')
                    if cap_idx == op_idx + 1:
                        column_names[op_idx] = 'Operational Capacity'
                        column_names.pop(cap_idx)
                
                # Process remaining columns
                standard_columns = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                                   "Population *", "% Pop to In Use CNA", "% Accommodation Available"]
                
                if len(column_names) != len(standard_columns):
                    print(f"Column mismatch in {file_path}. Using standard column names.")
                    column_names = standard_columns
                
                continue
            
            # Start collecting prison data rows after the header
            if in_data_section:
                # Check if this is the end of the data section
                if any(term in line for term in ["Sub total", "NOMS Operated", "Definitions of Accommodation", "Total"]):
                    prison_data_started = False
                    data_section_ended = True  # Set flag to indicate we've reached the end of data section
                    continue
                
                # Skip report date and page info lines
                if "Report Date:" in line or line.startswith("Page"):
                    continue
                
                # Check if this is a valid prison data row (starts with a prison name)
                # Prison names typically start with letters and are followed by numeric data
                # Only process if we haven't reached the end of the data section
                if not data_section_ended and re.match(r'^[A-Za-z]', line) and not line.startswith("Report") and not "Prison Name" in line:
                    prison_data_started = True
                    
                    # Split the line into parts
                    parts = line.split()
                    
                    # Find where the numeric data starts
                    numeric_start_idx = None
                    for j, part in enumerate(parts):
                        # Identify numeric or percentage data
                        if re.match(r'^\d', part) or part.startswith('%') or part.endswith('%'):
                            numeric_start_idx = j
                            break
                    
                    if numeric_start_idx is not None:
                        # Extract prison name and numeric data
                        prison_name = ' '.join(parts[:numeric_start_idx])
                        numeric_data = parts[numeric_start_idx:]
                        
                        # Add to data
                        if len(numeric_data) > 0:
                            data.append([prison_name] + numeric_data)
                    else:
                        # This might be just a prison name without numeric data
                        # (handle in the next iteration)
                        continue
        
        # If we didn't find column names, use default ones
        if not column_names:
            column_names = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                            "Population", "% Pop to In Use CNA", "% Accommodation Available"]
        
        # Create DataFrame
        if not data:
            print(f"No data extracted from RTF file: {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        
        # Handle column count mismatch
        if len(df.columns) != len(column_names):
            print(f"Warning: Column count mismatch in {os.path.basename(file_path)}")
            print(f"Found {len(df.columns)} columns, expected {len(column_names)}")
            
            # Adjust the number of columns
            if len(df.columns) > len(column_names):
                # Too many columns - use first columns matching the expected count
                df = df.iloc[:, :len(column_names)]
            else:
                # Too few columns - add empty columns
                for i in range(len(column_names) - len(df.columns)):
                    df[len(df.columns)] = None
        
        # Set column names
        df.columns = column_names
        
        # Convert numeric columns
        for col in df.columns:
            if col != "Prison Name":
                # Remove % symbols, commas and convert to numeric
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Extract report date from the file
        report_date = extract_report_date_from_file(file_path)
        if report_date:
            df['Report_Date'] = report_date
        
        # Standardize column names
        if 'Population' in df.columns and 'Population *' not in df.columns:
            df.rename(columns={'Population': 'Population *'}, inplace=True)
            
        # Drop rows where Prison Name is NaN or matches 'total'
        if 'Prison Name' in df.columns:
            df = df[df['Prison Name'].notna()]
            df = df[~df['Prison Name'].str.contains('total', case=False, na=False)]
            
        # Save the extracted data to CSV
        save_to_csv(df, file_path, output_path)
        
        return df
        
    except Exception as e:
        print(f"\nDetailed error in RTF extraction for {os.path.basename(file_path)}:")
        traceback.print_exc()
        return pd.DataFrame()
    

def extract_data_from_pdf(file_path: str, output_path: str) -> pd.DataFrame:
    """
    Extract prison data from PDF file
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        DataFrame with prison data
    """
    try:
        column_names = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                        "Population", "% Pop to In Use CNA", "% Accommodation Available"]
        
        all_data = []
        
        with pdfplumber.open(file_path) as pdf:
            # Process each page (excluding the definitions page)
            for page_num, page in enumerate(pdf.pages):
                # Skip the last page which typically contains definitions
                if page_num >= len(pdf.pages) - 1 and len(pdf.pages) > 1:
                    continue
                    
                # Extract text from the page
                text = page.extract_text()
                if not text:
                    continue
                    
                lines = text.split('\n')
                
                # Extract tabular data from the page
                data_rows = []
                in_data_section = False
                current_prison = None
                
                for line in lines:
                    # Convert to string and strip whitespace
                    if line is None:
                        continue
                    
                    line = str(line).strip()
                    
                    # Skip empty lines
                    if not line:
                        continue
                    
                    # Skip page number lines
                    try:
                        if re.match(r'^Page\s+\d+$', line) or re.match(r'^\d+$', line):
                            continue
                    except Exception:
                        # If regex fails, just continue with processing the line
                        pass
                    
                    # Check if we're in the header section
                    if ("Prison Name" in line and "Baseline" in line and "CNA" in line) or \
                       ("Prison Name" in line and "Population" in line):
                        in_data_section = True
                        continue
                    
                    # Skip report date lines
                    if "Report Date:" in line:
                        continue
                        
                    # Check if we've reached the end of the data section
                    if "Sub total" in line or "NOMS Operated" in line or "Definitions of Accommodation" in line:
                        in_data_section = False
                        continue
                    
                    if in_data_section:
                        # Split the line into white-space separated parts
                        parts = line.split()
                        
                        # Need at least the prison name and some numeric values
                        if len(parts) >= 2 and not parts[0].isdigit():
                            row_data = None  # Initialize to avoid reference errors
                            
                            # Detect if this is a continuation line for a multi-word prison name
                            has_numeric = False
                            for part in parts:
                                if re.match(r'\d', part) or part.endswith('%'):
                                    has_numeric = True
                                    break
                                    
                            if not has_numeric:
                                current_prison = line
                                continue
                                
                            # If this is a numeric data line that belongs to the current prison
                            elif current_prison and all(re.match(r'\d', part) or part.endswith('%') for part in parts):
                                row_data = [current_prison] + parts
                                current_prison = None  # Reset current prison
                            else:
                                # Find where the numeric data starts
                                numeric_start_idx = None
                                for i, part in enumerate(parts):
                                    if re.match(r'\d', part) or part.endswith('%'):
                                        numeric_start_idx = i
                                        break
                                
                                if numeric_start_idx is not None:
                                    prison_name = ' '.join(parts[:numeric_start_idx])
                                    numeric_data = parts[numeric_start_idx:]
                                    row_data = [prison_name] + numeric_data
                                else:
                                    # This might be just a prison name, remember it for the next line
                                    current_prison = line
                                    continue
                            
                            # If we have a valid row with close to the right number of fields, add it
                            if row_data and len(row_data) >= len(column_names) - 1:
                                # If we have too many fields, there might be split values due to spaces
                                if len(row_data) > len(column_names):
                                    # Try to merge prison name parts
                                    extra = len(row_data) - len(column_names)
                                    row_data[0] = ' '.join(row_data[:extra+1])
                                    row_data = [row_data[0]] + row_data[extra+1:]
                                
                                # If we still don't have the right number, pad or truncate
                                if len(row_data) < len(column_names):
                                    row_data = row_data + [None] * (len(column_names) - len(row_data))
                                elif len(row_data) > len(column_names):
                                    row_data = row_data[:len(column_names)]
                                
                                data_rows.append(row_data)
                
                all_data.extend(data_rows)
        
        # If we have no data, try a more relaxed parsing approach
        if not all_data:
            all_data = extract_data_from_pdf_relaxed(file_path)
    
    except Exception as e:
        print(f"Error parsing PDF {os.path.basename(file_path)}: {str(e)}")
        traceback.print_exc()
        # Try the relaxed approach as a fallback
        try:
            all_data = extract_data_from_pdf_relaxed(file_path)
        except Exception as e2:
            print(f"Error in relaxed PDF parsing for {os.path.basename(file_path)}: {str(e2)}")
            return pd.DataFrame()
    
    # Create DataFrame
    if all_data:
        df = pd.DataFrame(all_data, columns=column_names)
        
        # Convert numeric columns
        for col in df.columns:
            if col != "Prison Name":
                # Remove % symbols, commas and convert to numeric
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Extract report date from the file
        report_date = extract_report_date_from_file(file_path)
        if report_date:
            df['Report_Date'] = report_date
        
        # Standardize column names
        if 'Population' in df.columns and 'Population *' not in df.columns:
            df.rename(columns={'Population': 'Population *'}, inplace=True)
            
        # Drop rows where Prison Name is NaN or matches 'total'
        if 'Prison Name' in df.columns:
            df = df[df['Prison Name'].notna()]
            df = df[~df['Prison Name'].str.contains('total', case=False, na=False)]
            
        # Save the extracted data to CSV
        save_to_csv(df, file_path, output_path)
        
        return df
    else:
        print(f"No data extracted from PDF: {os.path.basename(file_path)}")
        return pd.DataFrame()
    

def extract_data_from_docx(file_path: str, output_path: str) -> pd.DataFrame:
    """
    Extract prison data from DOCX file
    
    Args:
        file_path: Path to the DOCX file
        
    Returns:
        DataFrame with prison data
    """
    try:
        # Convert DOCX to plain text
        text = docx_to_text(file_path)
        
        if not text:
            print(f"No text extracted from DOCX file: {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        # Process the text to extract tabular data
        # Split text into lines
        lines = text.split('\n')
        
        # Define column names based on the header in the file
        column_names = None
        data = []
        in_data_section = False
        prison_data_started = False
        data_section_ended = False  # Flag to indicate end of data section
        
        # First pass: identify column headers and prepare for data extraction
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Find the header row that contains "Prison Name"
            if "Prison Name" in line and ("Baseline" in line or "CNA" in line):
                # We've found the header row
                header_line = line
                in_data_section = True
                
                # Look for continuation of header in next line if needed
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and "Capacity" in next_line and not re.match(r'^[A-Za-z]', next_line):
                        # This is likely a continuation of the header
                        header_line += " " + next_line
                
                # Extract column names from header
                # For multi-part headers, use a more flexible regex
                header_parts = re.split(r'\s{2,}', header_line)
                column_names = [part.strip() for part in header_parts if part.strip()]
                
                # Fix common column name issues
                if 'Operational' in column_names and 'Capacity' in column_names:
                    # These might be split due to formatting
                    op_idx = column_names.index('Operational')
                    cap_idx = column_names.index('Capacity')
                    if cap_idx == op_idx + 1:
                        column_names[op_idx] = 'Operational Capacity'
                        column_names.pop(cap_idx)
                
                # Process remaining columns
                standard_columns = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                                   "Population *", "% Pop to In Use CNA", "% Accommodation Available"]
                
                if len(column_names) != len(standard_columns):
                    print(f"Column mismatch in {file_path}. Using standard column names.")
                    column_names = standard_columns
                
                continue
            
            # Start collecting prison data rows after the header
            if in_data_section:
                # Check if this is the end of the data section
                if any(term in line for term in ["Sub total", "NOMS Operated", "Definitions of Accommodation", "Total"]):
                    prison_data_started = False
                    data_section_ended = True  # Set flag to indicate we've reached the end of data section
                    continue
                
                # Skip report date and page info lines
                if "Report Date:" in line or line.startswith("Page"):
                    continue
                
                # Check if this is a valid prison data row (starts with a prison name)
                # Prison names typically start with letters and are followed by numeric data
                # Only process if we haven't reached the end of the data section
                if not data_section_ended and re.match(r'^[A-Za-z]', line) and not line.startswith("Report") and not "Prison Name" in line:
                    prison_data_started = True
                    
                    # Split the line into parts
                    parts = line.split()
                    
                    # Find where the numeric data starts
                    numeric_start_idx = None
                    for j, part in enumerate(parts):
                        # Identify numeric or percentage data
                        if re.match(r'^\d', part) or part.startswith('%') or part.endswith('%'):
                            numeric_start_idx = j
                            break
                    
                    if numeric_start_idx is not None:
                        # Extract prison name and numeric data
                        prison_name = ' '.join(parts[:numeric_start_idx])
                        numeric_data = parts[numeric_start_idx:]
                        
                        # Add to data
                        if len(numeric_data) > 0:
                            data.append([prison_name] + numeric_data)
                    else:
                        # This might be just a prison name without numeric data
                        # (handle in the next iteration)
                        continue
        
        # If we didn't find column names, use default ones
        if not column_names:
            column_names = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                            "Population", "% Pop to In Use CNA", "% Accommodation Available"]
        
        # Create DataFrame
        if not data:
            print(f"No data extracted from DOCX file: {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        
        # Handle column count mismatch
        if len(df.columns) != len(column_names):
            print(f"Warning: Column count mismatch in {os.path.basename(file_path)}")
            print(f"Found {len(df.columns)} columns, expected {len(column_names)}")
            
            # Adjust the number of columns
            if len(df.columns) > len(column_names):
                # Too many columns - use first columns matching the expected count
                df = df.iloc[:, :len(column_names)]
            else:
                # Too few columns - add empty columns
                for i in range(len(column_names) - len(df.columns)):
                    df[len(df.columns)] = None
        
        # Set column names
        df.columns = column_names
        
        # Convert numeric columns
        for col in df.columns:
            if col != "Prison Name":
                # Remove % symbols, commas and convert to numeric
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Extract report date from the file
        report_date = extract_report_date_from_file(file_path)
        if report_date:
            df['Report_Date'] = report_date
        
        # Standardize column names
        if 'Population' in df.columns and 'Population *' not in df.columns:
            df.rename(columns={'Population': 'Population *'}, inplace=True)
            
        # Drop rows where Prison Name is NaN or matches 'total'
        if 'Prison Name' in df.columns:
            df = df[df['Prison Name'].notna()]
            df = df[~df['Prison Name'].str.contains('total', case=False, na=False)]
            
        # Save the extracted data to CSV
        save_to_csv(df, file_path, output_path)
        
        return df
        
    except Exception as e:
        print(f"\nDetailed error in DOCX extraction for {os.path.basename(file_path)}:")
        traceback.print_exc()
        return pd.DataFrame()


def is_temp_file(file_path: str) -> bool:
    """
    Check if a file is a temporary/backup file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if it's a temporary file, False otherwise
    """
    filename = os.path.basename(file_path)
    return filename.startswith('~$')


def extract_data_from_doc(file_path: str, output_path: str) -> pd.DataFrame:
    """
    Extract prison data from DOC file
    
    Args:
        file_path: Path to the DOC file
        
    Returns:
        DataFrame with prison data
    """
    # Skip temporary files completely
    if is_temp_file(file_path):
        print(f"Skipping temporary file: {os.path.basename(file_path)}")
        return pd.DataFrame()
    
    try:
        # Convert DOC to plain text
        text = doc_to_text(file_path)
        
        # Check if we got any valid text
        valid_text = text and is_valid_doc_text(text)
        
        # If no text or invalid text, try converting to DOCX before giving up
        if not valid_text and platform.system() == 'Windows':
            print(f"No valid data extracted from DOC file: {os.path.basename(file_path)}")
            print(f"Attempting to convert to DOCX and reanalyze...")
            
            docx_path = convert_doc_to_docx(file_path)
            if docx_path and os.path.exists(docx_path):
                print(f"Successfully converted to DOCX. Attempting to extract data from {os.path.basename(docx_path)}")
                return extract_data_from_docx(docx_path)
            
            print(f"Conversion failed or DOCX extraction failed for {os.path.basename(file_path)}")
            return pd.DataFrame()
        
        if not text:
            print(f"No text extracted from DOC file: {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        # Validate the text content before processing
        if not is_valid_doc_text(text):
            print(f"Warning: Extracted text from {os.path.basename(file_path)} appears to be corrupted or not valid prison data.")
            return pd.DataFrame()
            
        # Process the text to extract tabular data
        # Split text into lines
        lines = text.split('\n')
        
        # Define column names based on the header in the file
        column_names = None
        data = []
        in_data_section = False
        prison_data_started = False
        data_section_ended = False  # Flag to indicate end of data section
        
        # First pass: identify column headers and prepare for data extraction
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Find the header row that contains "Prison Name"
            if "Prison Name" in line and ("Baseline" in line or "CNA" in line):
                # We've found the header row
                header_line = line
                in_data_section = True
                
                # Look for continuation of header in next line if needed
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and "Capacity" in next_line and not re.match(r'^[A-Za-z]', next_line):
                        # This is likely a continuation of the header
                        header_line += " " + next_line
                
                # Extract column names from header
                # For multi-part headers, use a more flexible regex
                header_parts = re.split(r'\s{2,}', header_line)
                column_names = [part.strip() for part in header_parts if part.strip()]
                
                # Fix common column name issues
                if 'Operational' in column_names and 'Capacity' in column_names:
                    # These might be split due to formatting
                    op_idx = column_names.index('Operational')
                    cap_idx = column_names.index('Capacity')
                    if cap_idx == op_idx + 1:
                        column_names[op_idx] = 'Operational Capacity'
                        column_names.pop(cap_idx)
                
                # Process remaining columns
                standard_columns = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                                   "Population *", "% Pop to In Use CNA", "% Accommodation Available"]
                
                if len(column_names) != len(standard_columns):
                    print(f"Column mismatch in {file_path}. Using standard column names.")
                    column_names = standard_columns
                
                continue
            
            # Start collecting prison data rows after the header
            if in_data_section:
                # Check if this is the end of the data section
                if any(term in line for term in ["Sub total", "NOMS Operated", "Definitions of Accommodation", "Total"]):
                    prison_data_started = False
                    data_section_ended = True  # Set flag to indicate we've reached the end of data section
                    continue
                
                # Skip report date and page info lines
                if "Report Date:" in line or line.startswith("Page"):
                    continue
                
                # Check if this is a valid prison data row (starts with a prison name)
                # Prison names typically start with letters and are followed by numeric data
                # Only process if we haven't reached the end of the data section
                if not data_section_ended and re.match(r'^[A-Za-z]', line) and not line.startswith("Report") and not "Prison Name" in line:
                    prison_data_started = True
                    
                    # Split the line into parts
                    parts = line.split()
                    
                    # Find where the numeric data starts
                    numeric_start_idx = None
                    for j, part in enumerate(parts):
                        # Identify numeric or percentage data
                        if re.match(r'^\d', part) or part.startswith('%') or part.endswith('%'):
                            numeric_start_idx = j
                            break
                    
                    if numeric_start_idx is not None:
                        # Extract prison name and numeric data
                        prison_name = ' '.join(parts[:numeric_start_idx])
                        numeric_data = parts[numeric_start_idx:]
                        
                        # Add to data
                        if len(numeric_data) > 0:
                            data.append([prison_name] + numeric_data)
                    else:
                        # This might be just a prison name without numeric data
                        # (handle in the next iteration)
                        continue
        
        # If we didn't find column names, use default ones
        if not column_names:
            column_names = ["Prison Name", "Baseline CNA", "In Use CNA", "Operational Capacity", 
                            "Population", "% Pop to In Use CNA", "% Accommodation Available"]
        
        # Create DataFrame
        if not data:
            print(f"No data extracted from DOC file: {os.path.basename(file_path)}")
            return pd.DataFrame()
            
        # Validate the extracted data
        if not validate_prison_data(data):
            print(f"Warning: Extracted data from {os.path.basename(file_path)} does not appear to be valid prison data.")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        
        # Handle column count mismatch
        if len(df.columns) != len(column_names):
            print(f"Warning: Column count mismatch in {os.path.basename(file_path)}")
            print(f"Found {len(df.columns)} columns, expected {len(column_names)}")
            
            # Adjust the number of columns
            if len(df.columns) > len(column_names):
                # Too many columns - use first columns matching the expected count
                df = df.iloc[:, :len(column_names)]
            else:
                # Too few columns - add empty columns
                for i in range(len(column_names) - len(df.columns)):
                    df[len(df.columns)] = None
        
        # Set column names
        df.columns = column_names
        
        # Convert numeric columns
        for col in df.columns:
            if col != "Prison Name":
                # Remove % symbols, commas and convert to numeric
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Extract report date from the file
        report_date = extract_report_date_from_file(file_path)
        if report_date:
            df['Report_Date'] = report_date
        
        # Standardize column names
        if 'Population' in df.columns and 'Population *' not in df.columns:
            df.rename(columns={'Population': 'Population *'}, inplace=True)
            
        # Drop rows where Prison Name is NaN or matches 'total'
        if 'Prison Name' in df.columns:
            df = df[df['Prison Name'].notna()]
            df = df[~df['Prison Name'].str.contains('total', case=False, na=False)]
            
        # Save the extracted data to CSV
        save_to_csv(df, file_path, output_path)
        
        return df
        
    except Exception as e:
        print(f"\nDetailed error in DOC extraction for {os.path.basename(file_path)}:")
        traceback.print_exc()
        return pd.DataFrame()


def validate_prison_data(data: List[List]) -> bool:
    """
    Validate if the extracted data appears to be valid prison data.
    
    Args:
        data: List of data rows extracted from a file
        
    Returns:
        Boolean indicating if the data appears valid
    """
    if not data or len(data) < 2:  # Need at least a few rows to be useful
        return False
        
    # Check if data has a reasonable structure
    row_lengths = [len(row) for row in data]
    if min(row_lengths) < 2 or max(row_lengths) > 10:
        return False
        
    # Check if prison names in first column look reasonable
    prison_names = [row[0] for row in data]
    
    # Prison names should be primarily alphabetic
    if not all(isinstance(name, str) and any(c.isalpha() for c in name) for name in prison_names):
        return False
        
    # Check if numeric data looks reasonable
    for row in data:
        numeric_values = row[1:] if len(row) > 1 else []
        for value in numeric_values:
            if value is None:
                continue
                
            # Try to convert to float
            try:
                float_val = float(str(value).replace(',', '').replace('%', ''))
                # Prison capacities are typically between 10 and 5000
                if isinstance(float_val, (int, float)) and (float_val < 0 or float_val > 10000):
                    return False
            except (ValueError, TypeError):
                # Some non-numeric values are okay, but not too many
                pass
                
    return True


def extract_data_from_pdf_relaxed(file_path: str) -> list:
    """
    Use a more relaxed approach to extract data from PDF file
    when the standard approach fails
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        List of data rows
    """
    all_data = []
    
    try:
        with pdfplumber.open(file_path) as pdf:
            # Extract tables from each page using pdfplumber's built-in table extraction
            for page in pdf.pages:
                tables = page.extract_tables()
                
                for table in tables:
                    # Skip empty tables or header-only tables
                    if len(table) <= 1:
                        continue
                    
                    # Check if this looks like a prison data table
                    header = table[0]
                    if any(keyword in ' '.join([str(h) for h in header if h is not None]) 
                           for keyword in ['Prison', 'CNA', 'Capacity']):
                        # Process rows, skipping the header
                        for row in table[1:]:
                            # Skip empty rows or "total" rows
                            if not row or not row[0] or (row[0] and 'total' in str(row[0]).lower()):
                                continue
                                
                            # Clean up row data
                            cleaned_row = []
                            for cell in row:
                                if cell is None:
                                    cleaned_row.append(None)
                                else:
                                    # Remove newlines and extra spaces
                                    cleaned_cell = str(cell).replace('\n', ' ').strip()
                                    cleaned_row.append(cleaned_cell)
                            
                            # Only add rows that start with a prison name (not numeric)
                            if cleaned_row[0] and not re.match(r'^\d', cleaned_row[0]):
                                all_data.append(cleaned_row)
    except Exception as e:
        print(f"Error in relaxed PDF parsing for {os.path.basename(file_path)}: {str(e)}")
        traceback.print_exc()
    
    return all_data
