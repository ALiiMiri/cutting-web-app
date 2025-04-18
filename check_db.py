import sqlite3
import os
import json
from datetime import datetime

def check_database(db_name='cutting_web_data.db'):
    """
    Enhanced function to check and display database structure and sample data
    """
    print(f"\n{'=' * 80}")
    print(f"DATABASE INSPECTION REPORT: {db_name}")
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}")
    
    # Check if database file exists
    if not os.path.exists(db_name):
        print(f"\n⚠️ ERROR: Database file '{db_name}' not found!")
        return
    
    # Get file info
    file_size = os.path.getsize(db_name)
    file_size_formatted = format_file_size(file_size)
    file_created = datetime.fromtimestamp(os.path.getctime(db_name)).strftime('%Y-%m-%d %H:%M:%S')
    file_modified = datetime.fromtimestamp(os.path.getmtime(db_name)).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n📊 DATABASE FILE INFORMATION:")
    print(f"  • Path: {os.path.abspath(db_name)}")
    print(f"  • Size: {file_size_formatted} ({file_size} bytes)")
    print(f"  • Created: {file_created}")
    print(f"  • Last Modified: {file_modified}")
    
    # Connect to the database
    try:
        conn = sqlite3.connect(db_name)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()
        print("\n✅ Successfully connected to the database.")
    except Exception as e:
        print(f"\n⚠️ ERROR connecting to database: {e}")
        return
    
    try:
        # Get SQLite version
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        print(f"  • SQLite Version: {version}")
        
        # Get database page size and other PRAGMA info
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        
        print(f"  • Page Size: {page_size} bytes")
        print(f"  • Page Count: {page_count}")
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        if not tables:
            print("\n⚠️ No tables found in the database!")
            conn.close()
            return
            
        print(f"\n📋 FOUND {len(tables)} TABLES:")
        for table_row in tables:
            table_name = table_row[0]
            if table_name == 'sqlite_sequence':
                continue  # Skip internal SQLite tables
                
            print(f"\n{'=' * 80}")
            print(f"TABLE: {table_name}")
            print(f"{'=' * 80}")
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print("\n📝 COLUMNS:")
            print(f"{'ID':3} | {'Name':25} | {'Type':12} | {'NotNull':7} | {'DefaultVal':15} | {'PK':2}")
            print("-" * 80)
            for col in columns:
                col_id, name, type_, not_null, default_val, pk = col
                print(f"{col_id:<3} | {name[:25]:<25} | {type_[:12]:<12} | {'✓' if not_null else '':^7} | {str(default_val)[:15]:<15} | {'✓' if pk else '':^2}")
            
            # Get foreign keys
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            fkeys = cursor.fetchall()
            if fkeys:
                print("\n🔗 FOREIGN KEYS:")
                print(f"{'ID':3} | {'Column':25} | {'References Table':20} | {'References Column':20} | {'On Update':12} | {'On Delete':12}")
                print("-" * 105)
                for fk in fkeys:
                    fk_id, seq, ref_table, from_col, to_col, on_update, on_delete, match = fk
                    print(f"{fk_id:<3} | {from_col[:25]:<25} | {ref_table[:20]:<20} | {to_col[:20]:<20} | {on_update[:12]:<12} | {on_delete[:12]:<12}")
            
            # Get indices
            cursor.execute(f"PRAGMA index_list({table_name})")
            indices = cursor.fetchall()
            if indices:
                print("\n🔍 INDICES:")
                print(f"{'Name':30} | {'Unique':6} | {'Created By':10} | {'Partial':7}")
                print("-" * 60)
                for idx in indices:
                    idx_name, idx_origin, idx_partial = idx[1], idx[2], idx[3]
                    idx_unique = idx[2] if len(idx) > 2 else 0
                    print(f"{idx_name[:30]:<30} | {'✓' if idx_unique else '':^6} | {idx_origin[:10]:<10} | {'✓' if idx_partial else '':^7}")
                    
                    # Get index details
                    cursor.execute(f"PRAGMA index_info({idx_name})")
                    idx_info = cursor.fetchall()
                    if idx_info:
                        print(f"  Columns: ", end="")
                        col_names = []
                        for info in idx_info:
                            col_id = info[1]
                            cursor.execute(f"PRAGMA table_info({table_name})")
                            cols = cursor.fetchall()
                            if col_id < len(cols):
                                col_names.append(cols[col_id][1])
                        print(", ".join(col_names))
            
            # Count rows
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            print(f"\n📊 TOTAL ROWS: {row_count}")
            
            # Get sample data (first 5 rows)
            if row_count > 0:
                print(f"\n📋 SAMPLE DATA (up to 5 rows):")
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                rows = cursor.fetchall()
                
                # Get column names for display
                column_names = [col[1] for col in columns]
                
                # Calculate column widths based on content
                col_widths = [min(len(name) + 2, 30) for name in column_names]
                for row in rows:
                    for i, val in enumerate(row):
                        if val is not None:
                            val_str = str(val)
                            if len(val_str) > col_widths[i]:
                                col_widths[i] = min(len(val_str) + 2, 30)
                
                # Display column headers
                header = " | ".join([f"{name[:col_widths[i]-2]:<{col_widths[i]}}" for i, name in enumerate(column_names)])
                print(header)
                print("-" * len(header))
                
                # Display data rows
                for row in rows:
                    row_data = " | ".join([format_cell_value(val, col_widths[i]) for i, val in enumerate(row)])
                    print(row_data)
                
                # Show distribution of values for small tables
                if row_count <= 100:
                    for i, col_name in enumerate(column_names):
                        # Skip large text fields
                        if "text" in columns[i][2].lower() and col_widths[i] >= 25:
                            continue
                            
                        cursor.execute(f"SELECT {col_name}, COUNT(*) as count FROM {table_name} GROUP BY {col_name} ORDER BY count DESC LIMIT 10")
                        value_counts = cursor.fetchall()
                        if len(value_counts) > 1 and len(value_counts) < row_count:
                            print(f"\n📊 Distribution for '{col_name}':")
                            for val, count in value_counts:
                                val_formatted = format_cell_value(val, 20)
                                percent = (count / row_count) * 100
                                bar_length = int(percent / 2)
                                print(f"  {val_formatted} : {count:4} ({percent:5.1f}%) {'█' * bar_length}")
    
    except Exception as e:
        print(f"\n⚠️ ERROR during database inspection: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        conn.close()
        print("\n✅ Database connection closed.")
        print(f"\n{'=' * 80}")

def format_file_size(size_bytes):
    """Format file size in readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def format_cell_value(value, width):
    """Format cell value for display with truncation"""
    if value is None:
        return f"{'NULL':<{width}}"
    elif isinstance(value, (int, float)):
        return f"{str(value):<{width}}"
    elif isinstance(value, str):
        if len(value) > width - 2:
            return f"{value[:width-5]+'...':<{width}}"
        return f"{value:<{width}}"
    else:
        val_str = str(value)
        if len(val_str) > width - 2:
            return f"{val_str[:width-5]+'...':<{width}}"
        return f"{val_str:<{width}}"

if __name__ == "__main__":
    check_database()
    
    # Uncomment below to inspect a different database file
    # check_database('other_database.db') 