"""
labels_callbacks: shared by the five labels_<layer> Script DATs.
Each one asks labels_lib for its own layer (named after the DAT), so a layer
recooks only when something that layer reads changes.
"""

def onCook(scriptOp: scriptDAT):
	rows = op('labels_lib').module.build(scriptOp.name.replace('labels_', '', 1))
	scriptOp.clear()
	scriptOp.appendRow(['x', 'y', 'text'])
	for row in rows:
		scriptOp.appendRow(row)
	return
