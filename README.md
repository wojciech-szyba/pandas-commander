# Pandas Commander
Lightweight portable os independent (works in Windows Terminal , Linux Shell, remote VPS, cloud isolated from external networks etc...) Pandas data multitool in one window

## Features
- Classic commander file manager (mkdir , new file , delete)
- Pandas files editor (view, edit, syntax highlighting , code autocompletion, running)
- Polars files editor (view, edit, syntax highlighting , code autocompletion, running)
- Python files editor (view, edit, syntax highlighting , code autocompletion, running)
- SQL files editor (view, edit, syntax highlighting , code autocompletion, running)
- Handy clasic command line with output in window 
- Pandas code snippets
- Autosave
- Multiple windows handling
- Results graphical visualisation
- CSV / JSON file viewer / editor
- Popular data files Pandas based viewer (generates pandas code and returns head after run triggered) / editor (csv, json , parquet, orc, avro ,feather, xlsx/xlsm, xml, tsv, pickle)


Stay tuned .. there will be more

# Installation guide

```
cd pandas-commander \
python3 -m venv pandascom \
pip install -r requirements.txt
```

# Run

```
source pandascom/bin/activate \
python3 pandas-commander.py
```

## Demo:
![Alt text](demo.gif)