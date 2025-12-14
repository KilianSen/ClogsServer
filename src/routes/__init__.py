from importlib import import_module
import os
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

def import_all_in_dir(path, pkg=__package__, is_root=True):
    for entry in os.scandir(path):
        if entry.is_dir():
            logger.info(f"Loading package: {pkg}.{entry.name}")
            import_all_in_dir(os.path.join(path, entry.name), pkg=f"{pkg}.{entry.name}", is_root=False)
            continue

        name, ext = os.path.splitext(entry.name)
        if ext != ".py" or not entry.is_file() or ("__init__" in name and is_root):
            logger.debug(f"Skipping file: {entry.name}")
            continue

        logger.info(f"Importing module: {pkg}.{name}")
        import_module(f".{name}", package=pkg)


import_all_in_dir(os.path.dirname(__file__))