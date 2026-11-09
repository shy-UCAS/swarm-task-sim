"""Read-only summary of durable resource samples; usable after an unexpected restart."""
import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def summarize(directory):
    directory=Path(directory)
    meta=json.loads((directory/"metadata.json").read_text(encoding="utf-8-sig"))
    result={"directory":str(directory),"metadata":meta,"samples":0,"invalid_lines":0,
            "first_utc":None,"last_utc":None,"max_sample_gap_s":0.,"sample_errors":0,
            "min_available_gib":None,"peak_committed_gib":0.,"peak_commit_percent":0.,
            "peak_cpu_percent":0.,"peak_processor_queue":0,"peak_python_count":0,"peak_python_private_gib":0.,
            "peak_pages_input_per_s":0.,"peak_page_reads_per_s":0.,"peak_disk_queue":0.,
            "by_job":{},"top_python_peaks":[]}
    previous=None
    processes={}
    jobs=defaultdict(lambda:{"samples":0,"min_available_gib":None,"peak_committed_gib":0.,"peak_cpu_percent":0.,"first_utc":None,"last_utc":None})
    with (directory/"metrics.jsonl").open(encoding="utf-8") as f:
        for line in f:
            try:
                row=json.loads(line)
            except (ValueError,UnicodeError):
                result["invalid_lines"]+=1
                continue
            if "sequence" not in row:
                result["last_event"]=row
                continue
            result["samples"]+=1
            now=datetime.fromisoformat(row["utc"].replace("Z","+00:00"))
            if previous is not None:
                result["max_sample_gap_s"]=max(result["max_sample_gap_s"],(now-previous).total_seconds())
            previous=now
            result["first_utc"]=result["first_utc"] or row["utc"]
            result["last_utc"]=row["utc"]
            result["sample_errors"]+=len(row.get("errors",[]))
            m,c=row.get("memory",{}),row.get("cpu",{})
            available=m.get("available_bytes")
            available=None if available is None else available/2**30
            committed=m.get("committed_bytes",0)/2**30
            if available is not None:
                result["min_available_gib"]=available if result["min_available_gib"] is None else min(result["min_available_gib"],available)
            for target,value in (("peak_committed_gib",committed),("peak_commit_percent",m.get("commit_percent",0)),
                ("peak_cpu_percent",c.get("busy_percent",0)),("peak_processor_queue",c.get("processor_queue",0)),
                ("peak_pages_input_per_s",m.get("pages_input_per_s",0)),("peak_page_reads_per_s",m.get("page_reads_per_s",0))):
                result[target]=max(result[target],value or 0)
            python=row.get("python",[])
            result["peak_python_count"]=max(result["peak_python_count"],len(python))
            total=sum(p.get("private_bytes",0) for p in python)/2**30
            result["peak_python_private_gib"]=max(result["peak_python_private_gib"],total)
            result["peak_disk_queue"]=max(result["peak_disk_queue"],max((d.get("queue",0) or 0 for d in row.get("disks",[])),default=0))
            for p in python:
                key=(p["pid"],p.get("start_utc"))
                before=processes.get(key)
                if before is None or p.get("private_bytes",0)>before.get("private_bytes",0):
                    processes[key]={**p,"at_utc":row["utc"]}
            job=row.get("job") or {}
            label=f"p{job.get('phase','-')}/{job.get('intent','idle')}/{job.get('round','-')}"
            j=jobs[label]
            j["samples"]+=1
            j["first_utc"]=j["first_utc"] or row["utc"]
            j["last_utc"]=row["utc"]
            if available is not None:
                j["min_available_gib"]=available if j["min_available_gib"] is None else min(j["min_available_gib"],available)
            j["peak_committed_gib"]=max(j["peak_committed_gib"],committed)
            j["peak_cpu_percent"]=max(j["peak_cpu_percent"],c.get("busy_percent",0) or 0)
    result["by_job"]=dict(jobs)
    result["top_python_peaks"]=sorted(processes.values(),key=lambda p:p.get("private_bytes",0),reverse=True)[:10]
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--out")
    args=parser.parse_args()
    summary=summarize(args.directory)
    text=json.dumps(summary,ensure_ascii=False,indent=1)+"\n"
    if args.out:
        target=Path(args.out)
        with target.open("x",encoding="utf-8",newline="\n") as f:
            f.write(text)
    else:
        print(text,end="")
