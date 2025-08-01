#!/usr/bin/env python3
# Program designed by James Brown, W0RLD
"""
ADIF Log File Parser - GUI Version
Parses ADIF log files and filters records based on LOTW_QSL_RCVD and QSL_RCVD status
"""

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Optional
import tempfile
import webbrowser
import datetime


class ADIFLogParser:
    def __init__(self):
        self.records = []
    
    def parse_file(self, file_path: str) -> bool:
        """Parse the ADIF log file and extract records"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Split records by <eor> (end of record)
            record_texts = content.split('<eor>')
            
            self.records = []
            for record_text in record_texts:
                if record_text.strip():  # Skip empty records
                    record = self.parse_record(record_text)
                    if record:
                        self.records.append(record)
            
            return True
            
        except Exception as e:
            raise Exception(f"Error reading file: {e}")
    
    def parse_record(self, record_text: str) -> Optional[Dict[str, str]]:
        """Parse a single ADIF record and extract field values"""
        record = {}
        
        # ADIF format: <field:length>value
        # Find all ADIF fields using regex
        field_pattern = r'<([^>:]+)(?::(\d+))?(?::[^>]*)?>\s*([^<]*)'
        matches = re.findall(field_pattern, record_text, re.IGNORECASE)
        
        for match in matches:
            field_name = match[0].upper()
            field_length = match[1]
            field_value = match[2].strip()
            
            # If length is specified, use only that many characters
            if field_length and field_length.isdigit():
                field_value = field_value[:int(field_length)]
            
            record[field_name] = field_value
        
        # Only return record if it has essential fields
        if record.get('CALL'):
            return record
        return None
    
    def is_record_confirmed(self, record: Dict[str, str]) -> bool:
        """Check if a record is confirmed by either LoTW or paper QSL"""
        lotw_rcvd = record.get('LOTW_QSL_RCVD', 'N')
        qsl_rcvd = record.get('QSL_RCVD', 'N')
        return lotw_rcvd == 'Y' or qsl_rcvd == 'Y'
    
    def sort_records_by_band(self, records: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Sort records by band in proper numerical order"""
        def band_sort_key(record):
            band = record.get('BAND', '').lower()
            # Extract numeric part from band (e.g., "20m" -> 20, "6m" -> 6)
            try:
                if 'm' in band:
                    return int(band.replace('m', ''))
                elif 'cm' in band:
                    return int(band.replace('cm', '')) / 100  # Convert cm to m equivalent
                else:
                    return 999  # Put unknown bands at the end
            except ValueError:
                return 999  # Put invalid bands at the end
        
        return sorted(records, key=band_sort_key, reverse=True)  # Reverse for 80, 40, 30, 20, 17, 15, 12, 6
    
    def filter_records(self, filter_type: str = "confirmed", band_filter: str = "all") -> List[Dict[str, str]]:
        """Filter records based on LOTW_QSL_RCVD and QSL_RCVD status and band"""
        filtered = []
        
        if filter_type == "confirmed":
            # Show only confirmed records (LoTW Y or paper QSL Y)
            for record in self.records:
                if self.is_record_confirmed(record):
                    filtered.append(record)
        elif filter_type == "confirmed_countries":
            # Show one record per confirmed country (DXCC)
            # First apply band filter, then get unique DXCC entities
            confirmed_records = []
            for record in self.records:
                if self.is_record_confirmed(record):
                    # Apply band filter at this stage if specified
                    if band_filter != "all":
                        if record.get('BAND', '').lower() != band_filter.lower():
                            continue
                    confirmed_records.append(record)
            
            # Sort by COUNTRY name alphabetically
            confirmed_records.sort(key=lambda x: x.get('COUNTRY', '').upper())
            
            # Get one record per DXCC
            seen_dxcc = set()
            for record in confirmed_records:
                dxcc = record.get('DXCC', '')
                if dxcc and dxcc not in seen_dxcc:
                    seen_dxcc.add(dxcc)
                    filtered.append(record)
            
            # Skip the general band filter later since we already applied it
            return filtered
        elif filter_type == "unconfirmed":
            # Show only unconfirmed records (neither LoTW nor paper QSL confirmed)
            for record in self.records:
                if not self.is_record_confirmed(record):
                    filtered.append(record)
        elif filter_type == "unconfirmed_no_qsl":
            # Show only unconfirmed records for DXCC entities that have no confirmed QSOs within the same band
            
            # First, build a set of (BAND, DXCC) combinations that have confirmed QSOs
            confirmed_band_dxcc = set()
            for record in self.records:
                if self.is_record_confirmed(record):
                    band = record.get('BAND', '')
                    dxcc = record.get('DXCC', '')
                    if band and dxcc:
                        confirmed_band_dxcc.add((band, dxcc))
            
            # Then filter unconfirmed records, excluding those where the same BAND+DXCC has a confirmed QSO
            for record in self.records:
                if not self.is_record_confirmed(record):
                    band = record.get('BAND', '')
                    dxcc = record.get('DXCC', '')
                    if band and dxcc:
                        # Only include if this BAND+DXCC combination has no confirmed QSOs
                        if (band, dxcc) not in confirmed_band_dxcc:
                            filtered.append(record)
                    else:
                        # Include records with missing BAND or DXCC data
                        filtered.append(record)
        else:  # "all"
            filtered = self.records.copy()
        
        # Apply band filter (skip if already applied for confirmed_countries)
        if band_filter != "all" and filter_type != "confirmed_countries":
            filtered = [record for record in filtered if record.get('BAND', '').lower() == band_filter.lower()]
        
        return filtered


class ADIFLogGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ADIF Log Parser")
        self.root.geometry("1000x700")
        self.parser = ADIFLogParser()
        self.current_file = None
        
        self.setup_ui()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # File selection frame
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)
        
        ttk.Label(file_frame, text="ADIF Log File:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var, state="readonly")
        self.file_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        ttk.Button(file_frame, text="Browse", command=self.browse_file).grid(row=0, column=2)
        
        # Filter frame
        filter_frame = ttk.LabelFrame(main_frame, text="Filter Options", padding="10")
        filter_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # QSL Status filters
        ttk.Label(filter_frame, text="QSL Status:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.filter_var = tk.StringVar(value="confirmed")
        ttk.Radiobutton(filter_frame, text="Confirmed records only (LOTW_QSL_RCVD = Y OR QSL_RCVD = Y)", 
                       variable=self.filter_var, value="confirmed").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Radiobutton(filter_frame, text="Confirmed countries (one record per DXCC)", 
                       variable=self.filter_var, value="confirmed_countries").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Radiobutton(filter_frame, text="Unconfirmed records only (neither LOTW nor paper QSL confirmed)", 
                       variable=self.filter_var, value="unconfirmed").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Radiobutton(filter_frame, text="Unconfirmed records (within a Band for DXCC entities with no confirmed QSL)", 
                       variable=self.filter_var, value="unconfirmed_no_qsl").grid(row=4, column=0, sticky=tk.W, pady=2)
        ttk.Radiobutton(filter_frame, text="All records", 
                       variable=self.filter_var, value="all").grid(row=5, column=0, sticky=tk.W, pady=2)
        
        # Band filters
        ttk.Label(filter_frame, text="Band:", font=('TkDefaultFont', 9, 'bold')).grid(row=6, column=0, sticky=tk.W, pady=(15, 5))
        
        self.band_var = tk.StringVar(value="all")
        
        # Create band filter buttons frame
        band_frame = ttk.Frame(filter_frame)
        band_frame.grid(row=7, column=0, sticky=tk.W, pady=2)
        
        # Common amateur radio bands
        bands = [
            ("All Bands", "all"),
            ("160m", "160m"),
            ("80m", "80m"),
            ("60m", "60m"),
            ("40m", "40m"),
            ("30m", "30m"),
            ("20m", "20m"),
            ("17m", "17m"),
            ("15m", "15m"),
            ("12m", "12m"),
            ("10m", "10m"),
            ("6m", "6m"),
            ("4m", "4m"),
            ("2m", "2m"),
            ("70cm", "70cm")
        ]
        
        # Arrange band buttons in multiple rows
        row = 0
        col = 0
        for band_text, band_value in bands:
            ttk.Radiobutton(band_frame, text=band_text, 
                           variable=self.band_var, value=band_value).grid(row=row, column=col, sticky=tk.W, padx=(0, 10), pady=1)
            col += 1
            if col > 4:  # 5 buttons per row
                col = 0
                row += 1
        
        # Button frame
        button_frame = ttk.Frame(filter_frame)
        button_frame.grid(row=8, column=0, pady=(15, 0))
        
        ttk.Button(button_frame, text="Apply Filter", command=self.apply_filter).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(button_frame, text="Export to File", command=self.export_results).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(button_frame, text="Print", command=self.print_results).grid(row=0, column=2)
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Results", padding="5")
        results_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Treeview for results - Updated column names
        columns = ('CALL', 'BAND', 'DXCC', 'COUNTRY', 'MODE', 'FREQ', 'LOTW-SENT', 'LOTW-RCVD', 'QSL-RCVD')
        self.tree = ttk.Treeview(results_frame, columns=columns, show='headings', height=15)
        
        # Define headings and column widths
        self.tree.heading('CALL', text='CALL')
        self.tree.heading('BAND', text='BAND')
        self.tree.heading('DXCC', text='DXCC')
        self.tree.heading('COUNTRY', text='COUNTRY')
        self.tree.heading('MODE', text='MODE')
        self.tree.heading('FREQ', text='FREQ')
        self.tree.heading('LOTW-SENT', text='LOTW-SENT')
        self.tree.heading('LOTW-RCVD', text='LOTW-RCVD')
        self.tree.heading('QSL-RCVD', text='QSL-RCVD')
        
        self.tree.column('CALL', width=100)
        self.tree.column('BAND', width=60)
        self.tree.column('DXCC', width=60)
        self.tree.column('COUNTRY', width=120)
        self.tree.column('MODE', width=60)
        self.tree.column('FREQ', width=80)
        self.tree.column('LOTW-SENT', width=80)
        self.tree.column('LOTW-RCVD', width=80)
        self.tree.column('QSL-RCVD', width=80)
        
        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Please select an ADIF log file")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
    
    def browse_file(self):
        """Open file dialog to select log file"""
        file_path = filedialog.askopenfilename(
            title="Select ADIF Log File",
            filetypes=[("ADIF files", "*.adi"), ("All files", "*.*")]
        )
        
        if file_path:
            self.file_path_var.set(file_path)
            self.load_file(file_path)
    
    def load_file(self, file_path):
        """Load and parse the log file"""
        try:
            self.parser.parse_file(file_path)
            self.current_file = file_path
            self.status_var.set(f"Loaded {len(self.parser.records)} records from {os.path.basename(file_path)}")
            self.apply_filter()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {str(e)}")
            self.status_var.set("Error loading file")
    
    def apply_filter(self):
        """Apply the selected filter and update the display"""
        if not self.parser.records:
            messagebox.showwarning("Warning", "No log file loaded")
            return
        
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Apply filter
        filter_type = self.filter_var.get()
        band_filter = self.band_var.get()
        
        records = self.parser.filter_records(filter_type, band_filter)
        
        # Sort records by band before displaying (except for confirmed_countries which is already sorted by DXCC)
        if filter_type != "confirmed_countries":
            records = self.parser.sort_records_by_band(records)
        
        # Populate treeview - Updated to include QSL_RCVD field
        for record in records:
            values = (
                record.get('CALL', ''),
                record.get('BAND', ''),
                record.get('DXCC', ''),
                record.get('COUNTRY', ''),
                record.get('MODE', ''),
                record.get('FREQ', ''),
                record.get('LOTW_QSL_SENT', ''),
                record.get('LOTW_QSL_RCVD', 'N'),
                record.get('QSL_RCVD', 'N')
            )
            self.tree.insert('', 'end', values=values)
        
        # Update status
        filter_names = {
            "confirmed": "confirmed", 
            "confirmed_countries": "confirmed countries (one per DXCC)",
            "unconfirmed": "unconfirmed", 
            "unconfirmed_no_qsl": "unconfirmed (no confirmed QSL for DXCC+Band)",
            "all": "all"
        }
        filter_name = filter_names.get(filter_type, filter_type)
        
        band_filter = self.band_var.get()
        band_text = f" on {band_filter}" if band_filter != "all" else ""
        
        self.status_var.set(f"Showing {len(records)} {filter_name} records{band_text}")
    
    def print_results(self):
        """Print filtered results by opening in browser print dialog"""
        if not self.tree.get_children():
            messagebox.showwarning("Warning", "No results to print")
            return
        
        try:
            # Create HTML content
            html_content = self.generate_html_report()
            
            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as temp_file:
                temp_file.write(html_content)
                temp_file_path = temp_file.name
            
            # Open in default browser (which will allow printing)
            webbrowser.open(f'file://{temp_file_path}')
            
            # Note: The temporary file will be cleaned up by the OS eventually
            # We could add cleanup logic, but it's not critical for this use case
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate print preview: {str(e)}")
    
    def generate_html_report(self) -> str:
        """Generate HTML report for printing"""
        # Get current filter info
        filter_names = {
            "confirmed": "Confirmed", 
            "confirmed_countries": "Confirmed Countries (one per DXCC)",
            "unconfirmed": "Unconfirmed", 
            "unconfirmed_no_qsl": "Unconfirmed (no confirmed QSL for DXCC+Band)",
            "all": "All"
        }
        filter_name = filter_names.get(self.filter_var.get(), self.filter_var.get())
        band_filter = self.band_var.get()
        band_text = f" on {band_filter}" if band_filter != "all" else ""
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>ADIF Log Report</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }}
                h1 {{
                    color: #333;
                    border-bottom: 2px solid #333;
                    padding-bottom: 10px;
                }}
                .filter-info {{
                    margin-bottom: 20px;
                    padding: 10px;
                    background-color: #f5f5f5;
                    border-radius: 5px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f2f2;
                    font-weight: bold;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .summary {{
                    margin-top: 20px;
                    font-weight: bold;
                }}
                @media print {{
                    body {{ margin: 0.5in; }}
                    .filter-info {{ background-color: transparent; }}
                }}
            </style>
        </head>
        <body>
            <h1>ADIF Log Report</h1>
            <div class="filter-info">
                <strong>Filter:</strong> {filter_name} records{band_text}<br>
                <strong>Source File:</strong> {os.path.basename(self.current_file) if self.current_file else 'Unknown'}<br>
                <strong>Generated:</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>CALL</th>
                        <th>BAND</th>
                        <th>DXCC</th>
                        <th>COUNTRY</th>
                        <th>MODE</th>
                        <th>FREQ</th>
                        <th>LOTW-SENT</th>
                        <th>LOTW-RCVD</th>
                        <th>QSL-RCVD</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Add table rows
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            html += "<tr>"
            for value in values:
                html += f"<td>{value}</td>"
            html += "</tr>"
        
        html += f"""
                </tbody>
            </table>
            <div class="summary">
                Total records: {len(self.tree.get_children())}
            </div>
        </body>
        </html>
        """
        
        return html
    
    def export_results(self):
        """Export filtered results to a text file"""
        if not self.tree.get_children():
            messagebox.showwarning("Warning", "No results to export")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Export Results",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    # Write header - Updated column headers
                    f.write(f"{'CALL':<12} {'BAND':<8} {'DXCC':<6} {'COUNTRY':<20} {'MODE':<8} {'FREQ':<10} {'LOTW-SENT':<10} {'LOTW-RCVD':<10} {'QSL-RCVD':<10}\n")
                    f.write("-" * 106 + "\n")
                    
                    # Write records
                    for item in self.tree.get_children():
                        values = self.tree.item(item, 'values')
                        f.write(f"{values[0]:<12} {values[1]:<8} {values[2]:<6} {values[3]:<20} {values[4]:<8} {values[5]:<10} {values[6]:<10} {values[7]:<10} {values[8]:<10}\n")
                    
                    f.write(f"\nTotal records: {len(self.tree.get_children())}\n")
                
                messagebox.showinfo("Success", f"Results exported to {file_path}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {str(e)}")


def main():
    root = tk.Tk()
    app = ADIFLogGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
