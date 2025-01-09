#!/usr/bin/env python3

import re
import os
import sys
import argparse
from urllib.parse import urlparse, urljoin
from collections import defaultdict
from datetime import datetime

class TreeNode:
    """
    Represents a node in the directory tree.
    """
    def __init__(self, name, is_dir=True):
        self.name = name
        self.is_dir = is_dir
        self.children = {}

    def add_child(self, child_name, is_dir=True):
        if child_name not in self.children:
            self.children[child_name] = TreeNode(child_name, is_dir)
        return self.children[child_name]

def extract_urls(file_path):
    """
    Extracts URLs from the given Feroxbuster output file.
    """
    url_pattern = re.compile(r'(https?://\S+)')
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                match = url_pattern.search(line)
                if match:
                    url = match.group(1).rstrip(' ,')
                    urls.append(url)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
    return urls

def is_dir(url):
    """
    Determines if the given URL represents a directory based on trailing slash.
    """
    return url.endswith('/')

def detect_base_url(urls):
    """
    Detects the base URL from the list of URLs.
    """
    if not urls:
        return None
    base_urls = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            base_urls.add(f"{parsed.scheme}://{parsed.netloc}")
    if len(base_urls) == 1:
        return list(base_urls)[0]
    elif len(base_urls) > 1:
        # Return the base URL with the most matches
        return max(base_urls, key=lambda x: sum(1 for url in urls if url.startswith(x)))
    return None

def build_tree(urls, base_url):
    """
    Builds a directory tree from the list of URLs.
    """
    root = TreeNode('/', is_dir=True)
    parsed_base = urlparse(base_url) if base_url else None
    for url in urls:
        parsed = urlparse(url)
        path = parsed.path
        if parsed_base and not path.startswith(parsed_base.path):
            # Adjust path relative to base_url
            path = urljoin(parsed_base.path, path) if parsed_base.path != '/' else path
        parts = path.strip('/').split('/')
        current_node = root
        for i, part in enumerate(parts):
            if not part:
                continue
            # Determine if this part is a directory
            part_is_dir = True if i < len(parts) - 1 or is_dir(url) else False
            current_node = current_node.add_child(part, is_dir=part_is_dir)
    return root

def count_directories(node, counts=None, current_path='/', unique_paths=None):
    """
    Counts the total directories and files, and organizes directory information.
    """
    if counts is None:
        counts = {
            'total_dirs': 0,
            'total_files': 0,
            'directories': defaultdict(lambda: {'path': '', 'subdirs': 0, 'files': 0, 'items': []})
        }
    if unique_paths is None:
        unique_paths = set()
    if node.is_dir:
        counts['total_dirs'] += 1
        path = os.path.join(current_path, node.name).replace('\\', '/').rstrip('/')
        if path not in unique_paths:
            unique_paths.add(path)
            counts['directories'][path]['path'] = path
        for child in node.children.values():
            if child.is_dir:
                counts['directories'][path]['subdirs'] += 1
            else:
                counts['directories'][path]['files'] += 1
                counts['directories'][path]['items'].append(child.name)
                counts['total_files'] += 1
            count_directories(child, counts, path + '/', unique_paths)
    return counts

def identify_important_files(urls):
    """
    Identifies important files based on predefined patterns.
    Only the file names and their extensions are considered, not directory names.
    """
    important_patterns = {
        'Password Managers': re.compile(r'\.(kdbx|1pif|psafe3|pwd|dat|bpw|lck)$', re.IGNORECASE),
        'Backup Files': re.compile(r'\.(bak|backup|old|wbk|bck|tmp)$', re.IGNORECASE),
        'Network Configuration Files': re.compile(r'\.(conf|cfg|ini|config|htaccess|htpasswd)$', re.IGNORECASE),
        'Database Files': re.compile(r'\.(sql|db|sqlite|sqlite3|mdb|accdb|frm|myd|myi)$', re.IGNORECASE),
        'Sensitive Filenames': re.compile(r'\b(admin|password|passwd)\b', re.IGNORECASE)
    }
    important_files = []
    for url in urls:
        parsed = urlparse(url)
        path = parsed.path
        filename = os.path.basename(path)
        if not filename:
            continue  # Skip if it's a directory
        # Check for sensitive filenames
        if important_patterns['Sensitive Filenames'].search(filename):
            truncated = truncate_to_parent(path)
            important_files.append({'display': truncated, 'url': url})
            continue
        # Check for important extensions
        for category, pattern in important_patterns.items():
            if category == 'Sensitive Filenames':
                continue  # Already checked
            if pattern.search(filename):
                truncated = truncate_to_parent(path)
                important_files.append({'display': truncated, 'url': url})
                break
    return important_files

def truncate_to_parent(path):
    """
    Truncates the path to parent_dir/filename.
    """
    parts = path.strip('/').split('/')
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    elif len(parts) == 1:
        return parts[0]
    else:
        return path

def categorize_source_files(urls):
    """
    Categorizes all files based on their extensions.
    Each file type has its own separate box.
    """
    extensions = defaultdict(list)
    
    for url in urls:
        parsed = urlparse(url)
        path = parsed.path
        if is_dir(url):
            continue  # Skip directories
        ext = os.path.splitext(path)[1].lower()
        if ext:
            extensions[ext].append(url)
    
    # Sort extensions alphabetically
    sorted_extensions = sorted(extensions.items(), key=lambda x: x[0])
    
    return sorted_extensions

def generate_full_directory_tree_html(root, base_url, prefix=''):
    """
    Generates an HTML representation of the full directory and file tree using nested lists.
    Includes visual lines connecting parent directories to subdirectories and files.
    Highlights important files with animations.
    """
    html = ""
    if root.name != '/':
        dir_url = urljoin(base_url, root.name + '/')
        html += f"{prefix}<li><a href='{dir_url}' class='dir-link'>{root.name}/</a>"
    else:
        html += f"{prefix}<li><span class='dir-name'>{root.name}</span>"

    if root.children:
        html += "<ul>"
        for child in sorted(root.children.values(), key=lambda x: (not x.is_dir, x.name.lower())):
            if child.is_dir:
                html += generate_full_directory_tree_html(child, base_url, prefix + "    ")
            else:
                # Determine if the file is important
                is_important = is_file_important(child.name)
                highlight_class = "important-file" if is_important else ""
                # Display parent_dir/filename
                parent_dir = os.path.basename(os.path.dirname(urlparse(child.name).path))
                display_name = f"{parent_dir}/{child.name}" if parent_dir else child.name
                file_url = urljoin(base_url, child.name)
                # Highlight file extension
                name_parts = child.name.rsplit('.', 1)
                if len(name_parts) == 2:
                    filename, extension = name_parts
                    highlighted = f"{filename}.<span class='file-ext'>{extension}</span>"
                else:
                    highlighted = child.name
                html += f"{prefix}    <li><a href='{file_url}' class='file-link {highlight_class}'>{display_name}</a></li>\n"
        html += "</ul>"
    html += "</li>\n"
    return html

def is_file_important(filename):
    """
    Checks if the file is important based on its name or extension.
    """
    important_extensions = [
        '.kdbx', '.1pif', '.psafe3', '.pwd', '.dat', '.bpw', '.lck',  # Password Managers
        '.bak', '.backup', '.old', '.wbk', '.bck', '.tmp',            # Backup Files
        '.conf', '.cfg', '.ini', '.config', '.htaccess', '.htpasswd',  # Network Configuration Files
        '.sql', '.db', '.sqlite', '.sqlite3', '.mdb', '.accdb', '.frm', '.myd', '.myi',  # Database Files
        '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf', '.pdf', '.odt', '.ods', '.odp', '.txt', '.log', '.json', '.xml', '.yaml', '.yml', '.csv', '.zip', '.rar', '.7z'  # Document & Miscellaneous
    ]
    sensitive_keywords = ['admin', 'password', 'passwd']
    filename_lower = filename.lower()
    # Check for sensitive keywords in the filename
    if any(keyword in filename_lower for keyword in sensitive_keywords):
        return True
    # Check for important extensions
    _, ext = os.path.splitext(filename_lower)
    if ext in important_extensions:
        return True
    return False

def generate_html_report(counts, important_files, categorized_files, output_path, base_url, urls, scan_datetime):
    """
    Generates the HTML report with the specified structure.
    """
    # Generate important files HTML
    if important_files:
        important_files_html = '<ul class="important-files">'
        for file in important_files:
            important_files_html += f'<li><a href="{file["url"]}" class="important-link" target="_blank">{file["display"]}</a></li>'
        important_files_html += '</ul>'
    else:
        important_files_html = '<p>No Important Files found.</p>'

    # Generate all files categorized by type
    if categorized_files:
        all_files_html = '<div class="all-files">'
        for ext, files in categorized_files:
            if files:
                # Sort files alphabetically
                sorted_files = sorted(files, key=lambda x: os.path.basename(urlparse(x).path).lower())
                # Determine if collapsible (more than 25 files)
                is_collapsible = len(sorted_files) > 25
                displayed_files = sorted_files[:25] if is_collapsible else sorted_files
                hidden_files = sorted_files[25:] if is_collapsible else []
                
                # Remove the dot from extension for display
                ext_display = ext[1:].upper() if ext.startswith('.') else ext.upper()
                
                all_files_html += f'''
                <div class="file-type-box">
                    <h3>{ext_display} Files ({len(files)})</h3>
                    <ul class="file-list">'''
                for full_url in displayed_files:
                    filename = os.path.basename(urlparse(full_url).path)
                    directory = os.path.dirname(urlparse(full_url).path).strip('/')
                    immediate_dir = os.path.basename(directory) if directory else ''
                    display_name = f"{immediate_dir}/{filename}" if immediate_dir else filename
                    all_files_html += f'<li><a href="{full_url}" class="file-link" target="_blank">{display_name}</a></li>'
                all_files_html += '</ul>'
                
                if is_collapsible:
                    all_files_html += '<ul class="file-list hidden-files">'
                    for full_url in hidden_files:
                        filename = os.path.basename(urlparse(full_url).path)
                        directory = os.path.dirname(urlparse(full_url).path).strip('/')
                        immediate_dir = os.path.basename(directory) if directory else ''
                        display_name = f"{immediate_dir}/{filename}" if immediate_dir else filename
                        all_files_html += f'<li><a href="{full_url}" class="file-link" target="_blank">{display_name}</a></li>'
                    all_files_html += '</ul>'
                    # Add toggle button
                    all_files_html += f'''
                    <button class="toggle-button" onclick="toggleFiles(this)">Show More</button>
                </div>'''
                else:
                    all_files_html += '</div>'
        all_files_html += '</div>'
    else:
        all_files_html = '<p>No Files Found.</p>'

    # Generate full directory tree
    full_directory_tree_html = '<ul class="full-directory-tree">' + generate_full_directory_tree_html(build_tree(urls, base_url), base_url) + '</ul>'

    # Construct the final HTML content with Ubuntu-like CSS and JavaScript for collapsible sections and animations
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Feroxbuster Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@400;700&display=swap" rel="stylesheet">
    <style>
        /* Ubuntu-Like Theme */
        body {{
            font-family: 'Ubuntu', sans-serif;
            background-color: #f5f5f5; /* Light background */
            color: #333333; /* Dark text for contrast */
            margin: 0;
            padding: 20px;
            animation: fadeIn 1s ease-in-out;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{
            color: #4B8BBE; /* Ubuntu blue */
            text-align: center;
            margin-bottom: 40px;
            font-size: 2.5em;
            font-weight: 700;
            border-bottom: 3px solid #4B8BBE;
            padding-bottom: 10px;
        }}
        h2, h3 {{
            color: #4B8BBE;
            font-weight: 700;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        .section {{
            background-color: #ffffff; /* White background for sections */
            border: 1px solid #dddddd;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            transition: box-shadow 0.3s ease;
        }}
        .section:hover {{
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
        }}
        .summary {{
            font-size: 1.1em;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 4px;
            margin-bottom: 20px;
            border: 1px solid #dddddd;
        }}
        .important-files {{
            list-style-type: none;
            padding-left: 0;
        }}
        .important-files li {{
            margin-bottom: 5px;
        }}
        .important-link {{
            color: #E74C3C; /* Red for important files */
            text-decoration: none;
            font-weight: bold;
            animation: blink 1s infinite;
        }}
        .important-link:hover {{
            text-decoration: underline;
        }}
        @keyframes blink {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
            100% {{ opacity: 1; }}
        }}
        .all-files {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }}
        .file-type-box {{
            background: #ffffff;
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #dddddd;
            flex: 1 1 250px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s, box-shadow 0.2s;
            max-height: 400px;
            overflow: hidden;
            position: relative;
        }}
        .file-type-box:hover {{
            transform: translateY(-5px);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.15);
        }}
        .file-type-box h3 {{
            color: #4B8BBE;
            margin-top: 0;
            font-size: 1.2em;
            border-bottom: 1px solid #dddddd;
            padding-bottom: 8px;
        }}
        .file-list a {{
            color: #4B8BBE;
            text-decoration: none;
            transition: color 0.2s;
        }}
        .file-list a:hover {{
            color: #2E86C1; /* Darker blue on hover */
            text-decoration: underline;
        }}
        .full-directory-tree {{
            list-style-type: none;
            padding-left: 20px;
        }}
        .full-directory-tree ul {{
            list-style-type: none;
            padding-left: 20px;
        }}
        .full-directory-tree li {{
            margin: 5px 0;
            position: relative;
            font-size: 0.95em;
        }}
        .full-directory-tree li::before {{
            content: '';
            position: absolute;
            top: 10px;
            left: -10px;
            border-left: 1px solid #4B8BBE;
            border-bottom: 1px solid #4B8BBE;
            width: 10px;
            height: 10px;
        }}
        .dir-link {{
            color: #4B8BBE;
            text-decoration: none;
            font-weight: 700;
        }}
        .dir-link:hover {{
            text-decoration: underline;
        }}
        .file-link {{
            color: #4B8BBE;
            text-decoration: none;
        }}
        .file-link:hover {{
            color: #2E86C1;
            text-decoration: underline;
        }}
        .file-ext {{
            color: #E74C3C; /* Red for file extensions */
            font-weight: bold;
        }}
        .important-file {{
            animation: highlight 2s infinite;
        }}
        @keyframes highlight {{
            0% {{ background-color: #fff; }}
            50% {{ background-color: #ffcccc; }}
            100% {{ background-color: #fff; }}
        }}
        .toggle-button {{
            background-color: #4B8BBE;
            color: #ffffff;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 10px;
            font-size: 0.9em;
            transition: background-color 0.2s;
        }}
        .toggle-button:hover {{
            background-color: #2E86C1;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        /* Responsive Design */
        @media (max-width: 768px) {{
            .all-files {{
                flex-direction: column;
            }}
            .file-type-box {{
                flex: 1 1 100%;
            }}
        }}
    </style>
    <script>
        function toggleFiles(button) {{
            var hiddenList = button.previousElementSibling;
            if (hiddenList.style.display === "none" || hiddenList.style.display === "") {{
                hiddenList.style.display = "block";
                button.textContent = "Show Less";
            }} else {{
                hiddenList.style.display = "none";
                button.textContent = "Show More";
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>Feroxbuster Report</h1>
        
        <!-- Report Summary -->
        <div class="section">
            <h2>Report Summary</h2>
            <div class="summary">
                <strong>Webserver URL:</strong> <a href="{base_url}" class="dir-link" target="_blank">{base_url if base_url else "N/A"}</a><br>
                <strong>Date/Time of Scan:</strong> {scan_datetime}
            </div>
        </div>

        <!-- Important Files -->
        <div class="section">
            <h2>Important Files</h2>
            {important_files_html}
        </div>

        <!-- All Files -->
        <div class="section">
            <h2>All Files</h2>
            {all_files_html}
        </div>

        <!-- Full Directory Tree -->
        <div class="section">
            <h2>Full Directory Tree</h2>
            <div class="full-directory-tree">
                {full_directory_tree_html}
            </div>
        </div>
    </div>
</body>
</html>"""

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Report generated successfully: {output_path}")
    except Exception as e:
        print(f"Error generating report: {e}")
        sys.exit(1)

def main():
    """
    Main function to parse arguments and generate the report.
    """
    parser = argparse.ArgumentParser(description="Feroxbuster HTML Report Generator")
    parser.add_argument("input_file", help="Path to the Feroxbuster output file")
    parser.add_argument("-o", "--output", default="ferox_report.html", 
                        help="Output HTML report file path (default: ferox_report.html)")
    parser.add_argument("-d", "--datetime", default=None, 
                        help="Date and time of the scan (e.g., '2023-10-01 12:30:00'). If not provided, current date/time is used.")
    args = parser.parse_args()

    if not os.path.isfile(args.input_file):
        print(f"Error: Input file '{args.input_file}' does not exist.")
        sys.exit(1)

    print("Extracting URLs...")
    urls = extract_urls(args.input_file)
    if not urls:
        print("No URLs found in input file")
        sys.exit(1)

    base_url = detect_base_url(urls)
    if base_url:
        print(f"Detected base URL: {base_url}")
    else:
        print("Warning: Could not determine a single base URL")

    print("Building directory tree...")
    root = build_tree(urls, base_url)
    
    print("Analyzing directories...")
    counts = count_directories(root)
    
    print("Identifying important files...")
    important_files = identify_important_files(urls)
    
    print("Categorizing all files...")
    categorized_files = categorize_source_files(urls)
    
    print("Preparing scan date/time...")
    if args.datetime:
        try:
            scan_datetime = datetime.strptime(args.datetime, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            print("Error: Date/time format should be 'YYYY-MM-DD HH:MM:SS'")
            sys.exit(1)
    else:
        scan_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print("Generating report...")
    generate_html_report(counts, important_files, categorized_files, args.output, base_url, urls, scan_datetime)

if __name__ == "__main__":
    main()
