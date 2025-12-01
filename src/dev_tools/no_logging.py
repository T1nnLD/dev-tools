from fastapi import Request
import logging

logger = logging.getLogger("uvicorn.access")

def no_logging(func):
    setattr(func, "_no_access_log", True)
    print(dir(func))
    return func

async def logging_filter(request: Request, call_next):
    endpoint = request.scope.get("endpoint")
    print(endpoint)

    if endpoint and getattr(endpoint, "_no_access_log", False):
        print("da")
        logger.disabled = True
        response = await call_next(request)
        logger.disabled = False
        return response

    return await call_next(request)
