"""Exploratory, non-clinical ML on a user's own symptom log."""
def analyze_patterns(entries):
    base = {"method":"KMeans exploratory clustering", "available":False,
            "notice":"Exploratory grouping of self-reported records only. This is not a prediction, diagnosis, or measure of medical risk."}
    usable = [e for e in entries if e.severity is not None]
    if len(usable) < 6:
        return {**base, "message":"Add at least 6 symptom records with severity to explore descriptive groupings.", "records_used":len(usable), "groups":[]}
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        # Features are descriptive self-reports, not clinical labels.
        matrix = np.array([[float(e.severity),
                            float(e.duration_hours or 0),
                            float(e.sleep_quality or 0),
                            float(e.cycle_day or 0)] for e in usable], dtype=float)
        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        scaled = StandardScaler().fit_transform(matrix)
        k = min(3, max(2, len(usable)//4))
        labels = KMeans(n_clusters=k, random_state=17, n_init=10).fit_predict(scaled)
        groups=[]
        for label in sorted(set(labels.tolist())):
            group=[usable[i] for i,v in enumerate(labels) if v==label]
            groups.append({"group":f"Pattern group {int(label)+1}", "records":len(group),
                           "average_severity":round(sum(e.severity for e in group)/len(group),1),
                           "symptoms":sorted({e.symptom.title() for e in group})[:8],
                           "dates":[e.recorded_on.isoformat() for e in group]})
        groups.sort(key=lambda g:(-g["records"],g["group"]))
        return {**base,"available":True,"records_used":len(usable),"groups":groups,
                "message":"The model groups records with similar entered feature values. Group membership can change as you add data and should not be interpreted as a health finding."}
    except ImportError:
        return {**base,"message":"ML dependencies are not installed. Install requirements.txt to enable exploratory clustering.","records_used":len(usable),"groups":[]}
    except Exception:
        return {**base,"message":"There was a problem analysing this record set. Your saved data has not been changed.","records_used":len(usable),"groups":[]}
