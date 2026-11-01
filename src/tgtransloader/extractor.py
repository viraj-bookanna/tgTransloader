from __future__ import annotations

import os

import multivolumefile
import py7zr
import rarfile
import zipfile


class Extractor:
    """Multi-format archive extractor (zip, rar, 7z, split 7z)."""

    def __init__(self, unrar_path: str = ""):
        if unrar_path:
            rarfile.UNRAR_TOOL = unrar_path

    def extract(self, input_file: str, output_folder: str, password: str | None = None) -> None:
        os.makedirs(output_folder, exist_ok=True)
        lower = input_file.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(input_file, "r") as zip_ref:
                if password is not None:
                    zip_ref.setpassword(password.encode("utf-8"))
                zip_ref.extractall(output_folder)
        elif lower.endswith(".rar"):
            with rarfile.RarFile(input_file, "r") as rar_ref:
                if password is not None:
                    rar_ref.setpassword(password)
                rar_ref.extractall(output_folder)
        elif lower.endswith(".7z"):
            with py7zr.SevenZipFile(input_file, "r", password=password) as z:
                z.extractall(output_folder)
        elif lower.endswith((".7z.001", ".7z.0001")):
            base = input_file.rsplit(".7z", 1)[0] + ".7z"
            with multivolumefile.open(base, mode="rb") as target:
                with py7zr.SevenZipFile(target, "r", password=password) as z:
                    z.extractall(output_folder)
        else:
            raise ValueError(f"unknown archive format: {input_file}")
