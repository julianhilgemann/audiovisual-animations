"""
stats_series: descriptive statistics of the cleaned monthly series.

Output columns: key, label, text (long display string), value (number),
short (compact string for the dashboard's stats column, <= 13 characters).
Recomputed only when clean_series changes.
"""
import numpy as np

_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def _mon(date: str) -> str:
	"""'2022-03' -> 'Mar 22'."""
	return '%s %s' % (_MONTHS[int(date[5:7]) - 1], date[2:4])

def onCook(scriptOp: scriptDAT):
	scriptOp.clear()
	scriptOp.appendRow(['key', 'label', 'text', 'value', 'short'])
	src = scriptOp.inputs[0] if scriptOp.inputs else None
	if src is None or src.numRows < 26:
		scriptOp.appendRow(['status', 'Status', 'no data -- pulse Fetch Series', 0, 'no data'])
		return
	dates = [c.val for c in src.col('date')[1:]]
	month = np.array([int(c) for c in src.col('month')[1:]])
	v = np.array([float(c) for c in src.col('value_bn')[1:]])
	n = len(v)
	def row(key, label, text, value, short):
		scriptOp.appendRow([key, label, text, '%.6g' % value, short])

	row('months', 'Observations', '%d months' % n, n, '%d months' % n)
	row('span', 'Span', '%s .. %s' % (dates[0], dates[-1]), (n - 1) / 12.0, '%.1f years' % ((n - 1) / 12.0))
	row('latest', 'Latest', '%.2f bn  (%s)' % (v[-1], dates[-1]), v[-1], '%.2f %s' % (v[-1], _mon(dates[-1])))
	yoy = (v[-1] / v[-13] - 1.0) * 100.0
	row('yoy', 'YoY change', '%+.1f %%' % yoy, yoy, '%+.1f %%' % yoy)
	row('mean', 'Mean / median', '%.2f / %.2f bn' % (v.mean(), np.median(v)), v.mean(),
		'%.1f / %.1f' % (v.mean(), np.median(v)))
	row('std', 'Std deviation', '%.2f bn  (cv %.0f %%)' % (v.std(), 100 * v.std() / v.mean()), v.std(),
		'%.2f cv%.0f%%' % (v.std(), 100 * v.std() / v.mean()))
	i_min, i_max = int(v.argmin()), int(v.argmax())
	row('min', 'Minimum', '%.2f bn  (%s)' % (v[i_min], dates[i_min]), v[i_min], '%.2f %s' % (v[i_min], _mon(dates[i_min])))
	row('max', 'Maximum', '%.2f bn  (%s)' % (v[i_max], dates[i_max]), v[i_max], '%.2f %s' % (v[i_max], _mon(dates[i_max])))
	# trend growth between the first and the last 12-month average
	years = (n - 12) / 12.0
	cagr = ((v[-12:].mean() / v[:12].mean()) ** (1.0 / years) - 1.0) * 100.0
	row('cagr', 'Trend growth (CAGR)', '%+.2f %% p.a.' % cagr, cagr, '%+.2f %%/yr' % cagr)
	# month-on-month log changes: volatility and seasonality
	chg = np.diff(np.log(v))
	vol = chg.std() * 100.0
	row('vol', 'Volatility m/m', '%.1f %%' % vol, vol, '%.1f %%' % vol)
	c = chg - chg.mean()
	acf12 = float((c[12:] * c[:-12]).sum() / (c * c).sum())
	row('acf12', 'Seasonality (ACF 12)', '%.2f' % acf12, acf12, '%.2f' % acf12)
	# seasonal profile: mean ratio to the centred 12-month average
	ma = np.convolve(v, np.ones(12) / 12.0, mode='same')
	ratio = v[6:-6] / ma[6:-6]
	profile = np.array([ratio[month[6:-6] == m].mean() for m in range(1, 13)])
	peak = int(profile.argmax())
	low = int(profile.argmin())
	row('season', 'Strong / weak month', '%s %+.0f %% / %s %+.0f %%' % (
		_MONTHS[peak], (profile[peak] - 1) * 100, _MONTHS[low], (profile[low] - 1) * 100),
		(profile[peak] - profile[low]) * 100,
		'%s%+.0f %s%+.0f' % (_MONTHS[peak], (profile[peak] - 1) * 100, _MONTHS[low], (profile[low] - 1) * 100))
	# deepest fall of the 12-month average from its running peak
	ma12 = np.convolve(v, np.ones(12) / 12.0, mode='valid')
	run_max = np.maximum.accumulate(ma12)
	dd = ma12 / run_max - 1.0
	i_dd = int(dd.argmin())
	i_pk = int(ma12[:i_dd + 1].argmax())
	row('drawdown', 'Max drawdown (12m avg)', '%.0f %%  (%s .. %s)' % (
		dd[i_dd] * 100, dates[i_pk + 11], dates[i_dd + 11]), dd[i_dd] * 100,
		'%.0f%% %s>%s' % (dd[i_dd] * 100, dates[i_pk + 11][2:4], dates[i_dd + 11][2:4]))
	return

def onGetCookLevel(scriptOp: scriptDAT) -> CookLevel:
	return CookLevel.AUTOMATIC
