"""
clean_series: Bundesbank CSV (raw_csv) -> typed monthly table.

Keeps only rows whose first cell is a YYYY-MM period and whose value parses as
a finite number (the API writes '.' or nothing for missing observations).
Columns: date, year, month, t (decimal year, mid-month), value_meur, value_bn.
"""
import csv
import io
import math
import re

_PERIOD = re.compile(r'^(\d{4})-(\d{2})$')

def onCook(scriptOp: scriptDAT):
	scriptOp.clear()
	scriptOp.appendRow(['date', 'year', 'month', 't', 'value_meur', 'value_bn'])
	raw = scriptOp.inputs[0].text if scriptOp.inputs else ''
	rows = {}
	for cells in csv.reader(io.StringIO(raw)):
		if len(cells) < 2:
			continue
		match = _PERIOD.match(cells[0].strip())
		if not match:
			continue
		try:
			value = float(cells[1].strip().replace(' ', ''))
		except ValueError:
			continue
		if not math.isfinite(value):
			continue
		rows[cells[0].strip()] = (int(match.group(1)), int(match.group(2)), value)
	for date in sorted(rows):
		year, month, value = rows[date]
		scriptOp.appendRow([date, year, month, '%.4f' % (year + (month - 0.5) / 12.0),
							'%g' % value, '%.4f' % (value / 1000.0)])
	return

def onGetCookLevel(scriptOp: scriptDAT) -> CookLevel:
	return CookLevel.AUTOMATIC
