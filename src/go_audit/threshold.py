"""Frozen-grid calibration and deployment diagnostics."""
from __future__ import annotations
from collections import defaultdict
import numpy as np
from .metrics import evaluate
from .semantics import threshold_sets, filter_sets

def curve(scores,terms,truth,indices,thresholds,boundary,universe,pe,re):
 rows=[]
 for tau in thresholds:
  pred=filter_sets(threshold_sets(scores[list(indices)],terms,tau,boundary),universe)
  metric=evaluate(pred,[truth[i] for i in indices],pe,re); rows.append({"threshold":tau,**metric})
 return rows
def first_max(rows): return max(rows,key=lambda row:(row["protein_f1"],-row["threshold"]))
def plateau(rows,tolerance):
 best=first_max(rows); i=rows.index(best); ok=[row["protein_f1"]>=best["protein_f1"]-tolerance-1e-15 for row in rows]; lo=hi=i
 while lo and ok[lo-1]:lo-=1
 while hi+1<len(rows) and ok[hi+1]:hi+=1
 return {"low":rows[lo]["threshold"],"high":rows[hi]["threshold"],"width":rows[hi]["threshold"]-rows[lo]["threshold"],"points":hi-lo+1}
def bootstrap_thresholds(scores,terms,truth,indices,groups,thresholds,boundary,universe,pe,re,draws,seed):
 grouped=defaultdict(list)
 for i in indices: grouped[groups[i]].append(i)
 blocks=[grouped[key] for key in sorted(grouped)]; rng=np.random.default_rng(seed); selected=[]
 for _ in range(draws):
  sample=[i for block in rng.integers(0,len(blocks),len(blocks)) for i in blocks[block]]
  selected.append(first_max(curve(scores,terms,truth,sample,thresholds,boundary,universe,pe,re))["threshold"])
 values=np.asarray(selected,float); unique,counts=np.unique(values,return_counts=True)
 return selected,{"median":float(np.median(values)),"sd":float(values.std()),"iqr":float(np.quantile(values,.75)-np.quantile(values,.25)),"q025":float(np.quantile(values,.025,method="linear")),"q975":float(np.quantile(values,.975,method="linear")),"frequency":{str(float(k)):int(v) for k,v in zip(unique,counts)}}
