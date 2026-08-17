"""Curated data-related shell one-liners for the command-line snippets picker.

Each entry is `(os_tag, label, command)`:
  - `os_tag` is "bash" (Linux/macOS, GNU-ish coreutils), "macos" (BSD
    userland variants worth calling out separately), or "pwsh" (Windows
    PowerShell / pwsh on any OS).
  - `label` is the short description shown in the picker.
  - `command` is inserted verbatim into the command line when chosen.

Placeholders like file.csv / column / pattern are meant to be edited by the
user after insertion, same as the editor snippet pickers.
"""
from __future__ import annotations

CliSnippet = tuple[str, str, str]

CLI_SNIPPETS: list[CliSnippet] = [
    # ----------------------------------------------------- bash / zsh (POSIX)
    ("bash", "Line count", "wc -l file.csv"),
    ("bash", "Line count of all CSVs", "wc -l *.csv"),
    ("bash", "Row count (no header)", "tail -n +2 file.csv | wc -l"),
    ("bash", "Column count", "head -1 file.csv | awk -F',' '{print NF}'"),
    ("bash", "Preview first rows", "head -n 20 file.csv"),
    ("bash", "Header only", "head -1 file.csv"),
    ("bash", "Pretty table view", "column -s, -t file.csv | less -S"),
    ("bash", "Unique values of a column", "cut -d',' -f2 file.csv | sort -u"),
    ("bash", "Value counts of a column", "cut -d',' -f2 file.csv | sort | uniq -c | sort -rn"),
    ("bash", "Sum a numeric column", "awk -F',' '{sum+=$3} END {print sum}' file.csv"),
    ("bash", "Filter rows matching pattern", "grep -i \"pattern\" file.csv"),
    ("bash", "Remove duplicate lines", "sort file.csv | uniq > dedup.csv"),
    ("bash", "Random sample of rows", "shuf -n 100 file.csv > sample.csv"),
    ("bash", "Split into chunks", "split -l 100000 file.csv chunk_"),
    ("bash", "Merge CSVs (single header)", "awk 'FNR==1 && NR!=1{next} {print}' *.csv > merged.csv"),
    ("bash", "Replace text in place", "sed -i 's/old/new/g' file.csv"),
    ("bash", "Strip CRLF line endings", "sed -i 's/\\r$//' file.csv"),
    ("bash", "Diff two sorted files", "diff <(sort a.csv) <(sort b.csv)"),
    ("bash", "Find files by name", "find . -name \"*.csv\""),
    ("bash", "Find files modified in last 24h", "find . -mtime -1 -type f"),
    ("bash", "Find largest files", "find . -type f -exec du -h {} + | sort -rh | head -20"),
    ("bash", "Disk usage per directory", "du -sh */ | sort -rh"),
    ("bash", "Disk free", "df -h"),
    ("bash", "Count files in directory", "find . -maxdepth 1 -type f | wc -l"),
    ("bash", "Search text recursively", "grep -rn \"TODO\" --include=\"*.py\" ."),
    ("bash", "Watch a log file live", "tail -f app.log"),
    ("bash", "SHA-256 checksum", "sha256sum file.csv"),
    ("bash", "Pretty-print JSON", "jq . file.json"),
    ("bash", "Extract field from JSON array", "jq -r '.[].field' file.json"),
    ("bash", "JSON array to CSV", "jq -r '(.[0] | keys_unsorted) as $k | $k, (.[] | [.[$k[]]]) | @csv' file.json"),
    ("bash", "Compress a file", "gzip -k file.csv"),
    ("bash", "Decompress a file", "gunzip file.csv.gz"),
    ("bash", "Create tar.gz archive", "tar czf archive.tar.gz folder/"),
    ("bash", "Extract tar.gz archive", "tar xzf archive.tar.gz"),
    ("bash", "Top IPs in an access log", "awk '{print $1}' access.log | sort | uniq -c | sort -rn | head"),
    ("bash", "Download a file", "curl -LO https://example.com/data.csv"),
    ("bash", "Top memory-consuming processes", "ps aux --sort=-%mem | head"),
    ("bash", "File type detection", "file data.bin"),
    ("bash", "Word count", "wc -w file.txt"),
    ("bash", "Base64 encode a file", "base64 file.bin > file.b64"),
    ("bash", "Count occurrences of a value", "grep -c \"value\" file.csv"),
    # ------------------------------------------------------- macOS (BSD)
    ("macos", "SHA-256 checksum", "shasum -a 256 file.csv"),
    ("macos", "MD5 checksum", "md5 file.csv"),
    ("macos", "Replace text in place", "sed -i '' 's/old/new/g' file.csv"),
    ("macos", "Random sample of lines", "sort -R file.csv | head -n 100 > sample.csv"),
    ("macos", "Human-readable disk usage", "du -sh -- * | sort -rh"),
    ("macos", "File info / metadata", "stat -x file.csv"),
    ("macos", "Open file in default app", "open file.csv"),
    ("macos", "Copy stdout to clipboard", "cat file.csv | pbcopy"),
    # ------------------------------------------------------- PowerShell
    ("pwsh", "Preview first rows", "Import-Csv .\\file.csv | Select-Object -First 10"),
    ("pwsh", "Row count", "(Import-Csv .\\file.csv).Count"),
    ("pwsh", "Group by and count", "Import-Csv .\\file.csv | Group-Object ColumnName | Sort-Object Count -Descending"),
    ("pwsh", "Filter rows", "Import-Csv .\\file.csv | Where-Object { $_.ColumnName -eq \"value\" }"),
    ("pwsh", "Select columns and export", "Import-Csv .\\file.csv | Select-Object Col1,Col2 | Export-Csv out.csv -NoTypeInformation"),
    ("pwsh", "Sum a numeric column", "(Import-Csv .\\file.csv | Measure-Object -Property Amount -Sum).Sum"),
    ("pwsh", "Random sample of rows", "Import-Csv .\\file.csv | Get-Random -Count 100 | Export-Csv sample.csv -NoTypeInformation"),
    ("pwsh", "Pretty table view", "Import-Csv .\\file.csv | Format-Table -AutoSize"),
    ("pwsh", "Convert CSV to JSON", "Import-Csv .\\file.csv | ConvertTo-Json | Set-Content out.json"),
    ("pwsh", "Pretty-print JSON", "Get-Content file.json | ConvertFrom-Json | ConvertTo-Json -Depth 10"),
    ("pwsh", "Find files", "Get-ChildItem -Recurse -Filter *.csv"),
    ("pwsh", "Find largest files", "Get-ChildItem -Recurse | Sort-Object Length -Descending | Select-Object -First 20 FullName,Length"),
    ("pwsh", "Disk usage per folder", "Get-ChildItem | ForEach-Object { [PSCustomObject]@{Name=$_.Name; SizeMB=((Get-ChildItem $_.FullName -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB)} } | Sort-Object SizeMB -Descending"),
    ("pwsh", "Free disk space", "Get-PSDrive -PSProvider FileSystem"),
    ("pwsh", "Tail a log file", "Get-Content app.log -Wait -Tail 20"),
    ("pwsh", "Search text recursively", "Get-ChildItem -Recurse -Include *.py | Select-String \"TODO\""),
    ("pwsh", "Compute file hash", "Get-FileHash file.csv -Algorithm SHA256"),
    ("pwsh", "Remove duplicate lines", "Get-Content file.csv | Sort-Object -Unique | Set-Content dedup.csv"),
    ("pwsh", "Replace text in file", "(Get-Content file.csv) -replace 'old','new' | Set-Content file.csv"),
    ("pwsh", "Count lines", "(Get-Content file.csv).Count"),
    ("pwsh", "Compress to zip", "Compress-Archive -Path .\\folder -DestinationPath archive.zip"),
    ("pwsh", "Expand zip archive", "Expand-Archive -Path archive.zip -DestinationPath .\\out"),
    ("pwsh", "Download a file", "Invoke-WebRequest -Uri https://example.com/data.csv -OutFile data.csv"),
    ("pwsh", "Top memory-consuming processes", "Get-Process | Sort-Object WS -Descending | Select-Object -First 10 Name,WS"),
]

OS_LABELS: dict[str, str] = {"bash": "bash/zsh", "macos": "macOS", "pwsh": "PowerShell"}
