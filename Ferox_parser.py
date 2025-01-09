#!/usr/bin/env python3

import re
import os
import sys
import argparse
from urllib.parse import urlparse, urljoin
from collections import defaultdict

class TreeNode:
    """
    Represents a node in the directory tree.
    """
    def __init__(self, name, is_dir=True):
        self.name = name  # Name of the directory or file
        self.is_dir = is_dir  # True if directory, False if file
        self.children = {}  # key: name, value: TreeNode

    def add_child(self, child_name, is_dir=True):
        if child_name not in self.children:
            self.children[child_name] = TreeNode(child_name, is_dir)
        return self.children[child_name]

    def __repr__(self):
        return f"TreeNode(name='{self.name}', is_dir={self.is_dir})"

def extract_urls(file_path):
    """
    Extracts all URLs starting with http:// or https:// from the given file.
    Skips lines that do not contain URLs.
    """
    url_pattern = re.compile(r'(https?://\S+)')
    urls = []
    with open(file_path, 'r') as file:
        for line in file:
            match = url_pattern.search(line)
            if match:
                # Extract the URL and remove any trailing characters like spaces or commas
                url = match.group(1).rstrip(' ,')
                # Remove any trailing slashes for consistency
                url = url.rstrip('/')
                urls.append(url)
    return urls

def is_file(path):
    """
    Determines if the given path points to a file based on its extension.
    """
    # Consider files with extensions or those that match certain patterns
    return bool(os.path.splitext(path)[1])

def build_tree(urls, base_url):
    """
    Builds a directory tree from the list of URLs.
    """
    parsed_base = urlparse(base_url)
    root = TreeNode('/', is_dir=True)

    for url in urls:
        parsed = urlparse(url)
        path = parsed.path

        # Ensure the URL starts with the base URL path
        if not path.startswith(parsed_base.path):
            # Adjust path if necessary
            path = path  # Modify as needed based on your specific base path requirements

        parts = path.strip('/').split('/')
        current_node = root

        for i, part in enumerate(parts):
            if part == '':
                continue  # Skip empty parts resulting from leading '/'
            # Determine if this part is a directory or file
            if i < len(parts) - 1:
                # Intermediate parts are directories
                current_node = current_node.add_child(part, is_dir=True)
            else:
                # Last part: determine if it's a file or directory
                if is_file(part):
                    current_node.add_child(part, is_dir=False)
                else:
                    current_node = current_node.add_child(part, is_dir=True)

    return root

def traverse_tree(node, parent_path='', grouped_urls=None, base_url=''):
    """
    Traverses the tree to collect URLs grouped by directories.
    """
    if grouped_urls is None:
        grouped_urls = defaultdict(list)

    current_path = os.path.join(parent_path, node.name)
    if node.is_dir:
        # Normalize directory path
        if parent_path == '' and node.name == '/':
            directory = base_url + '/'
        else:
            directory = urljoin(base_url + '/', current_path.strip('/'))
            if not directory.endswith('/'):
                directory += '/'
        for child in node.children.values():
            traverse_tree(child, current_path, grouped_urls, base_url)
    else:
        # It's a file; associate it with its parent directory
        directory = urljoin(base_url + '/', parent_path.strip('/') + '/')
        file_url = urljoin(directory, node.name)
        grouped_urls[directory].append(file_url)

    return grouped_urls

def count_directories(node, counts=None):
    """
    Recursively counts total directories and tracks subdirectories and files per directory.
    """
    if counts is None:
        counts = {
            'total_dirs': 0,
            'directories': defaultdict(lambda: {'subdirs': 0, 'files': 0})
        }

    if node.is_dir:
        counts['total_dirs'] += 1
        current_dir = '/' + node.name.strip('/') + '/' if node.name != '/' else '/'
        for child in node.children.values():
            if child.is_dir:
                counts['directories'][current_dir]['subdirs'] += 1
            else:
                counts['directories'][current_dir]['files'] += 1
        for child in node.children.values():
            count_directories(child, counts)

    return counts

def detect_base_url(urls):
    """
    Detects the base URL from the list of URLs.
    Assumes all URLs share the same base URL.
    """
    if not urls:
        return None
    parsed = urlparse(urls[0])
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return base_url

def identify_interesting_files(urls):
    """
    Identifies interesting files based on predefined patterns.
    Returns a dictionary categorizing these files.
    """
    patterns = {
        'Configuration/Environment Files': re.compile(r'\.(env|env\.bak|config\.php|config\.js|config\.xml|web\.config|\.htaccess|\.htpasswd|php\.ini|settings\.py|appsettings\.json)$', re.IGNORECASE),
        'Backup/Temporary Files': re.compile(r'\.(bak|backup|old|tmp|temp|swp|save|copy|orig)$|~\w+$', re.IGNORECASE),
        'Database Files': re.compile(r'\.(sql|db|sqlite|sqlite3|mdb|dbf|dump\.sql|backup\.sql)$', re.IGNORECASE),
        'Source Code': re.compile(r'\.(git|svn|hg)/|\.php_|\.inc$|\.phps$|\.java$|\.cs$|\.py$', re.IGNORECASE),
        'Log Files': re.compile(r'\.(log)$|error_log$|access_log$|debug\.log$|application\.log$', re.IGNORECASE),
        'Archive Files': re.compile(r'\.(zip|tar|gz|tar\.gz|rar|7z)$', re.IGNORECASE)
    }

    interesting_files = defaultdict(list)

    for url in urls:
        file_name = os.path.basename(url)
        for category, pattern in patterns.items():
            if pattern.search(file_name):
                interesting_files[category].append(url)
                break  # Avoid multiple categorizations

    return interesting_files

def generate_html_report(counts, grouped_urls, interesting_files, output_path, base_url):
    """
    Generates an HTML report with the summary, interesting files, and grouped URLs.
    """
    # Start HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Feroxbuster Report</title>
    <style>
        /* Google-inspired Clean and Modern Design */
        body {{
            font-family: 'Roboto', sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            width: 95%;
            max-width: 1400px;
            margin: 20px auto;
        }}
        h1 {{
            text-align: center;
            color: #4285F4;
            margin-bottom: 40px;
        }}
        .box {{
            background-color: #fff;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .box h2 {{
            border-bottom: 2px solid #4285F4;
            padding-bottom: 10px;
            color: #333;
            margin-top: 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 12px;
            border-bottom: 1px solid #ddd;
            text-align: left;
        }}
        th {{
            background-color: #4285F4;
            color: #fff;
        }}
        tr:hover {{
            background-color: #f1f1f1;
        }}
        .interesting-files {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }}
        .category-box {{
            flex: 1 1 300px;
            background-color: #e8f0fe;
            padding: 15px;
            border-left: 5px solid #4285F4;
            border-radius: 4px;
        }}
        .category-box h3 {{
            margin-top: 0;
            color: #4285F4;
        }}
        .category-box ul {{
            list-style-type: none;
            padding-left: 0;
        }}
        .category-box li {{
            margin-bottom: 8px;
        }}
        .url-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }}
        .directory-box {{
            background-color: #fff;
            padding: 15px;
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            width: calc(50% - 20px); /* Two boxes per row with gap */
            box-sizing: border-box;
        }}
        .directory-box h3 {{
            margin-top: 0;
            color: #4285F4;
            font-size: 1.2em;
        }}
        .directory-box ul {{
            list-style-type: none;
            padding-left: 0;
        }}
        .directory-box li {{
            margin-bottom: 5px;
            word-break: break-all;
        }}
        a {{
            color: #4285F4;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        @media (max-width: 1024px) {{
            .directory-box {{
                width: calc(50% - 20px); /* Two boxes per row */
            }}
        }}
        @media (max-width: 768px) {{
            .directory-box {{
                width: 100%; /* Single column on smaller screens */
            }}
            .interesting-files {{
                flex-direction: column;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Feroxbuster HTML Report</h1>
        
        <!-- Summary Section -->
        <div class="box">
            <h2>Summary</h2>
            <table>
                <tr>
                    <th>Total Directories Found</th>
                </tr>
                <tr>
                    <td>{counts['total_dirs']}</td>
                </tr>
            </table>
            
            <h3>Main Directories and Their Details</h3>
            <table>
                <tr>
                    <th>Directory</th>
                    <th>Subdirectories</th>
                    <th>Files</th>
                </tr>
"""
    # Add summary rows
    for directory, info in sorted(counts['directories'].items()):
        html_content += f"""                <tr>
                    <td><a href="{directory}" target="_blank">{directory}</a></td>
                    <td>{info['subdirs']}</td>
                    <td>{info['files']}</td>
                </tr>
"""
    html_content += """            </table>
        </div>
        
        <!-- Interesting Files Section -->
"""
    if interesting_files:
        html_content += """        <div class="box">
            <h2>Interesting Files</h2>
            <div class="interesting-files">
"""
        for category, files in sorted(interesting_files.items()):
            if files:
                html_content += f"""                <div class="category-box">
                    <h3>{category} ({len(files)})</h3>
                    <ul>
"""
                for file_url in sorted(files):
                    html_content += f'                        <li><a href="{file_url}" target="_blank">{file_url}</a></li>\n'
                html_content += """                    </ul>
                </div>
"""
        html_content += """            </div>
        </div>
"""
    else:
        html_content += """        <div class="box">
            <h2>Interesting Files</h2>
            <p>No interesting files found.</p>
        </div>
"""

    # Grouped URLs Section
    html_content += """        <div class="box">
            <h2>Grouped URLs</h2>
            <div class="url-list">
"""
    for directory in sorted(grouped_urls.keys()):
        html_content += f"""                <div class="directory-box">
                    <h3>Directory: <a href="{directory}" target="_blank">{directory}</a></h3>
                    <ul>
"""
        for url in sorted(grouped_urls[directory]):
            html_content += f'                        <li><a href="{url}" target="_blank">{url}</a></li>\n'
        html_content += """                    </ul>
                </div>
"""
    html_content += """            </div>
        </div>
    </div>
</body>
</html>"""

    # Write to the output HTML file
    try:
        with open(output_path, 'w') as f:
            f.write(html_content)
        print(f"HTML report successfully generated at '{output_path}'.")
    except Exception as e:
        print(f"Error writing HTML report to '{output_path}': {e}")

def main():
    parser = argparse.ArgumentParser(description="Parse Feroxbuster output, group URLs by directory, identify interesting files, and generate a modern HTML report.")
    parser.add_argument('input_file', help="Path to the Feroxbuster output file.")
    parser.add_argument('-o', '--output_file', help="Path to save the HTML report. Default is 'ferox_report.html'.", default='ferox_report.html')

    args = parser.parse_args()
    input_file = args.input_file
    output_file = args.output_file

    if not os.path.isfile(input_file):
        print(f"Error: The file '{input_file}' does not exist.")
        sys.exit(1)

    # Extract URLs from the file
    urls = extract_urls(input_file)
    if not urls:
        print("No URLs found in the file.")
        sys.exit(0)

    # Detect base URL
    base_url = detect_base_url(urls)
    if not base_url:
        print("Error: Could not determine base URL. Please ensure the input file contains valid URLs.")
        sys.exit(1)
    print(f"Detected Base URL: {base_url}\n")

    # Identify interesting files
    interesting_files = identify_interesting_files(urls)

    # Build directory tree
    tree_root = build_tree(urls, base_url)

    # Count directories, subdirectories, and files
    counts = count_directories(tree_root)

    # Traverse tree to group URLs
    grouped_urls = traverse_tree(tree_root, base_url=base_url)

    # Generate HTML report
    generate_html_report(counts, grouped_urls, interesting_files, output_file, base_url)

if __name__ == "__main__":
    main()
