from argus.adapters.base import CheckResult
import uuid
import time

def make_job(product: dict) -> dict:
    return {
        "job_id": str(uuid.uuid4()),
        "product": dict(product),           # passing in a copy
        "dispatched_ts": time.time(),
        "v": 1
    }

def make_result(job_id: str, product_id: str, result: CheckResult, worker_id: str) -> dict:
    return  {
        "job_id": job_id,
        "product_id": product_id,
        "status": result.status.value,                     
        "latency_ms": result.latency_ms,
        "error": result.error,               
        "error_kind": result.error_kind.value,                  
        "retry_after_s": result.retry_after_s,
        "worker_id": worker_id,
        "completed_ts": time.time(),
        "v": 1
    }

def make_heartbeat(worker_id: str, jobs_completed: int, current_job_id: str | None) -> dict:    
    return {
        "worker_id": worker_id,
        "ts": time.time(),
        "jobs_completed": jobs_completed,              # since worker startup
        "current_job_id": current_job_id,
        "v": 1
    }