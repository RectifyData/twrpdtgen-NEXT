# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Cloud-assisted Samsung firmware slicing.

The heavy Samsung FUS download stays on the cloud host. Only the selected
partition payload needs to be transferred back to the user's machine.
"""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
from typing import BinaryIO, Iterable, Optional
from urllib.request import Request, urlopen
import zipfile

import lz4.frame


SAMLOADER_RELEASE_API = (
    "https://api.github.com/repos/topjohnwu/samloader-rs/releases/latest"
)
USER_AGENT = "twrpdtgen-NEXT-cloud-slice/1"
PACKAGE_ORDER = ("AP", "BL", "CP", "CSC", "HOME_CSC", "USERDATA", "OTHER")
COPY_BUFFER = 1024 * 1024


class CloudSliceError(RuntimeError):
    """Raised when firmware download or slicing cannot be completed safely."""


@dataclass(frozen=True)
class SliceResult:
    firmware: Path
    package_member: str
    payload_member: str
    output: Path
    output_size: int
    sha256: str
    compression: str


def _request_headers(*, github_api: bool = False) -> dict:
    headers = {"User-Agent": USER_AGENT}
    if github_api:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(url: str) -> dict:
    request = Request(
        url,
        headers=_request_headers(github_api=True),
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _download_file(url: str, destination: Path) -> None:
    request = Request(url, headers=_request_headers())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=60) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out, COPY_BUFFER)


def _host_asset_key(
        system: Optional[str] = None,
        machine: Optional[str] = None,
) -> str:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()

    if machine in ("x86_64", "amd64", "x64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        raise CloudSliceError(
            f"Unsupported host architecture for samloader bootstrap: {machine}"
        )

    if system == "linux":
        return f"linux-{arch}"
    if system == "windows":
        return f"windows-{arch}"
    if system == "darwin":
        return "macos-universal"
    raise CloudSliceError(
        f"Unsupported host OS for samloader bootstrap: {system}"
    )


def select_samloader_asset(
        release: dict,
        system: Optional[str] = None,
        machine: Optional[str] = None,
) -> dict:
    """Choose the matching prebuilt samloader-rs release asset."""
    key = _host_asset_key(system=system, machine=machine)
    candidates = []
    for asset in release.get("assets", []):
        name = str(asset.get("name", "")).lower()
        if key in name and name.endswith(".zip"):
            candidates.append(asset)
    if len(candidates) != 1:
        names = ", ".join(
            str(asset.get("name", "")) for asset in release.get("assets", [])
        )
        raise CloudSliceError(
            f"Expected exactly one samloader asset for {key}; "
            f"found {len(candidates)}. Release assets: {names}"
        )
    return candidates[0]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(COPY_BUFFER), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_samloader(
        executable: Optional[Path] = None,
        cache_root: Optional[Path] = None,
) -> Path:
    """Return a usable samloader executable, installing a verified release if needed."""
    if executable is not None:
        executable = Path(executable)
        if not executable.is_file():
            raise CloudSliceError(f"samloader executable does not exist: {executable}")
        return executable

    found = shutil.which("samloader")
    if found:
        return Path(found)

    release = _request_json(SAMLOADER_RELEASE_API)
    asset = select_samloader_asset(release)
    tag = str(release.get("tag_name") or "latest")
    cache_root = Path(cache_root or Path.home() / ".cache" / "twrpdtgen-next")
    install_dir = cache_root / "samloader" / tag
    exe_name = "samloader.exe" if platform.system().lower() == "windows" else "samloader"
    installed = install_dir / exe_name
    if installed.is_file():
        return installed

    download_url = asset.get("browser_download_url")
    if not download_url:
        raise CloudSliceError("samloader release asset has no download URL")

    install_dir.mkdir(parents=True, exist_ok=True)
    archive = install_dir / str(asset["name"])
    _download_file(str(download_url), archive)

    expected = str(asset.get("digest") or "")
    if expected.startswith("sha256:"):
        actual = _sha256_file(archive)
        wanted = expected.split(":", 1)[1].lower()
        if actual.lower() != wanted:
            archive.unlink(missing_ok=True)
            raise CloudSliceError(
                "samloader release archive SHA-256 mismatch; refusing to execute it"
            )

    with zipfile.ZipFile(archive) as bundle:
        members = [
            item for item in bundle.infolist()
            if Path(item.filename).name.lower() == exe_name.lower()
            and not item.is_dir()
        ]
        if len(members) != 1:
            raise CloudSliceError(
                f"samloader release archive contains {len(members)} executable matches"
            )
        with bundle.open(members[0]) as source, installed.open("wb") as out:
            shutil.copyfileobj(source, out, COPY_BUFFER)

    if platform.system().lower() != "windows":
        mode = installed.stat().st_mode
        installed.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    archive.unlink(missing_ok=True)
    return installed


def download_firmware(
        model: str,
        region: str,
        destination: Path,
        *,
        version: Optional[str] = None,
        threads: int = 8,
        samloader: Optional[Path] = None,
) -> Path:
    """Download and decrypt Samsung firmware on the current host via samloader-rs."""
    if threads < 1:
        raise ValueError("threads must be at least 1")
    model = model.strip()
    region = region.strip()
    if not model or not region:
        raise ValueError("model and region are required")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Firmware destination already exists: {destination}")

    samloader_path = ensure_samloader(samloader)
    command = [
        str(samloader_path),
        "download",
        "-m",
        model,
        "-r",
        region,
        "-j",
        str(threads),
        "-o",
        str(destination),
    ]
    if version:
        command.extend(["-v", version.strip()])

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        destination.unlink(missing_ok=True)
        raise CloudSliceError(
            f"samloader firmware download failed with exit code {exc.returncode}"
        ) from exc

    if not destination.is_file():
        raise CloudSliceError(
            "samloader returned successfully but the expected firmware ZIP was not created"
        )
    if not zipfile.is_zipfile(destination):
        destination.unlink(missing_ok=True)
        raise CloudSliceError(
            "samloader output is not a valid decrypted firmware ZIP"
        )
    return destination


def _package_kind(name: str) -> str:
    base = Path(name).name.upper()
    if base.startswith("HOME_CSC_"):
        return "HOME_CSC"
    for prefix in ("AP_", "BL_", "CP_", "CSC_", "USERDATA_"):
        if base.startswith(prefix):
            return prefix[:-1]
    return "OTHER"


def _preferred_package(partition: str) -> str:
    name = Path(partition).name.lower()
    for suffix in (".lz4", ".img", ".bin"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    if name in {
        "modem", "modem_debug", "cp_debug", "cp_mem", "dsp",
    }:
        return "CP"
    if name in {
        "sboot", "abl", "xbl", "xbl_config", "cm", "tz", "tzsw",
        "up_param", "keystorage", "steady", "uh", "bksecapp",
    }:
        return "BL"
    if name in {
        "cache", "prism", "optics", "omr", "carrier",
    }:
        return "CSC"
    return "AP"


def _firmware_packages(
        bundle: zipfile.ZipFile,
        package: str = "auto",
) -> list[zipfile.ZipInfo]:
    packages = [
        info
        for info in bundle.infolist()
        if not info.is_dir()
        and info.filename.lower().endswith((".tar.md5", ".tar"))
    ]
    if not packages:
        raise CloudSliceError("Firmware ZIP contains no TAR/TAR.MD5 packages")

    if package.lower() != "auto":
        wanted = package.upper()
        filtered = [
            info
            for info in packages
            if _package_kind(info.filename) == wanted
            or Path(info.filename).name.upper() == wanted
        ]
        if not filtered:
            available = ", ".join(Path(info.filename).name for info in packages)
            raise CloudSliceError(
                f"Requested package {package!r} was not found. Available: {available}"
            )
        return filtered

    rank = {name: index for index, name in enumerate(PACKAGE_ORDER)}
    return sorted(
        packages,
        key=lambda info: (
            rank.get(_package_kind(info.filename), len(rank)),
            Path(info.filename).name,
        ),
    )


def _payload_candidates(partition: str) -> set[str]:
    name = Path(partition).name.strip().lower()
    if not name:
        raise ValueError("partition must not be empty")
    if name.endswith(".lz4"):
        return {name}
    if name.endswith((".img", ".bin")):
        return {name, f"{name}.lz4"}
    return {
        name,
        f"{name}.img",
        f"{name}.img.lz4",
        f"{name}.bin",
        f"{name}.bin.lz4",
        f"{name}.lz4",
    }


def _infer_output_name(payload_member: str) -> str:
    name = Path(payload_member).name
    if name.lower().endswith(".lz4"):
        name = name[:-4]
    return name


def _default_output_for_partition(partition: str) -> Path:
    name = Path(partition).name
    if name.lower().endswith(".lz4"):
        name = name[:-4]
    if name.lower().endswith((".img", ".bin")):
        return Path(name)
    return Path(f"{name}.img")


def _copy_payload(
        source: BinaryIO,
        payload_member: str,
        destination: Path,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("wb") as out:
            if payload_member.lower().endswith(".lz4"):
                try:
                    with lz4.frame.open(source, mode="rb") as decoded:
                        shutil.copyfileobj(decoded, out, COPY_BUFFER)
                except (RuntimeError, ValueError, lz4.frame.LZ4FrameError) as exc:
                    raise CloudSliceError(
                        f"{payload_member} is not a supported LZ4 frame"
                    ) from exc
                compression = "lz4"
            else:
                shutil.copyfileobj(source, out, COPY_BUFFER)
                compression = "none"
        os.replace(temporary, destination)
        return compression
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def slice_firmware(
        firmware: Path,
        partition: str,
        *,
        output: Optional[Path] = None,
        package: str = "auto",
        member: Optional[str] = None,
        overwrite: bool = False,
) -> SliceResult:
    """Stream one partition from Samsung firmware without unpacking full TAR packages."""
    firmware = Path(firmware)
    if not firmware.is_file():
        raise FileNotFoundError(f"Firmware ZIP does not exist: {firmware}")
    if not zipfile.is_zipfile(firmware):
        raise CloudSliceError(f"Not a valid firmware ZIP: {firmware}")

    candidates = _payload_candidates(member or partition)
    exact_member = member.lower() if member else None

    with zipfile.ZipFile(firmware) as bundle:
        packages = _firmware_packages(bundle, package=package)
        if package.lower() == "auto":
            preferred = _preferred_package(partition)
            packages = sorted(
                packages,
                key=lambda info: (
                    _package_kind(info.filename) != preferred,
                    PACKAGE_ORDER.index(_package_kind(info.filename))
                    if _package_kind(info.filename) in PACKAGE_ORDER
                    else len(PACKAGE_ORDER),
                    Path(info.filename).name,
                ),
            )
        for package_info in packages:
            with bundle.open(package_info) as package_stream:
                try:
                    tar = tarfile.open(fileobj=package_stream, mode="r|*")
                except tarfile.TarError as exc:
                    raise CloudSliceError(
                        f"Unable to read {package_info.filename} as a TAR stream"
                    ) from exc

                with tar:
                    for tar_member in tar:
                        if not tar_member.isfile():
                            continue
                        base = Path(tar_member.name).name.lower()
                        full = tar_member.name.lower()
                        matched = (
                            full == exact_member
                            or base == Path(exact_member).name.lower()
                            if exact_member is not None
                            else base in candidates
                        )
                        if not matched:
                            continue

                        source = tar.extractfile(tar_member)
                        if source is None:
                            raise CloudSliceError(
                                f"Could not stream payload {tar_member.name}"
                            )
                        destination = Path(
                            output or _infer_output_name(tar_member.name)
                        )
                        if destination.exists() and not overwrite:
                            raise FileExistsError(
                                f"Output already exists: {destination}"
                            )

                        with source:
                            compression = _copy_payload(
                                source, tar_member.name, destination
                            )
                        size = destination.stat().st_size
                        digest = _sha256_file(destination)
                        return SliceResult(
                            firmware=firmware,
                            package_member=package_info.filename,
                            payload_member=tar_member.name,
                            output=destination,
                            output_size=size,
                            sha256=digest,
                            compression=compression,
                        )

    package_names = ", ".join(Path(item.filename).name for item in packages)
    wanted = member or partition
    raise CloudSliceError(
        f"Payload {wanted!r} was not found in firmware packages: {package_names}"
    )


def _print_result(result: SliceResult) -> None:
    print()
    print("Cloud slice complete")
    print(f"  package: {result.package_member}")
    print(f"  payload: {result.payload_member}")
    print(f"  output:  {result.output}")
    print(f"  size:    {result.output_size} bytes")
    print(f"  sha256:  {result.sha256}")
    print(f"  decoded: {result.compression}")


def _colab_download(path: Path) -> None:
    try:
        from google.colab import files  # type: ignore
    except ImportError as exc:
        raise CloudSliceError(
            "--colab-download was requested outside Google Colab"
        ) from exc
    files.download(str(path))


def _add_slice_options(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--partition",
        required=True,
        help="partition/payload name, e.g. boot, recovery, init_boot, vendor_boot",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="final standalone payload path; defaults to the TAR payload filename",
    )
    parser.add_argument(
        "--package",
        default="auto",
        help="limit search to AP, BL, CP, CSC, HOME_CSC, USERDATA, or exact package name",
    )
    parser.add_argument(
        "--member",
        help="exact TAR member path/name override instead of partition-name matching",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing final payload",
    )
    parser.add_argument(
        "--colab-download",
        action="store_true",
        help="trigger a browser download of only the final payload in Google Colab",
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m twrpdtgen.cloud_slice",
        description=(
            "Cloud-assisted Samsung firmware slicing: download/decrypt the full "
            "firmware on the cloud host, stream only one partition from the "
            "nested TAR package, and keep only the final payload for local download."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser(
        "fetch",
        help="download/decrypt firmware with samloader-rs, then extract one payload",
    )
    fetch.add_argument("-m", "--model", required=True, help="Samsung model, e.g. SM-G975F")
    fetch.add_argument("-r", "--region", required=True, help="CSC region, e.g. BTU or EUX")
    fetch.add_argument(
        "-v",
        "--version",
        help="specific firmware version; omit to use the latest available",
    )
    fetch.add_argument(
        "-j",
        "--threads",
        type=int,
        default=8,
        help="samloader parallel connections (default: 8)",
    )
    fetch.add_argument(
        "--samloader",
        type=Path,
        help="existing samloader-rs executable; otherwise a verified release is bootstrapped",
    )
    fetch.add_argument(
        "--work-dir",
        type=Path,
        help="cloud work directory; defaults to a temporary directory",
    )
    fetch.add_argument(
        "--keep-firmware",
        action="store_true",
        help="keep the full decrypted firmware ZIP in the cloud work directory",
    )
    _add_slice_options(fetch)

    local = sub.add_parser(
        "slice",
        help="slice an already-downloaded decrypted Samsung firmware ZIP",
    )
    local.add_argument("firmware", type=Path)
    _add_slice_options(local)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    if args.command == "slice":
        result = slice_firmware(
            args.firmware,
            args.partition,
            output=args.output,
            package=args.package,
            member=args.member,
            overwrite=args.overwrite,
        )
        _print_result(result)
        if args.colab_download:
            _colab_download(result.output)
        return 0

    output = args.output or _default_output_for_partition(args.partition)
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Output already exists: {output}")

    if args.work_dir or args.keep_firmware:
        work_dir = Path(args.work_dir or Path.cwd() / ".twrpdtgen-cloud")
        work_dir.mkdir(parents=True, exist_ok=True)
        temporary_context = None
    else:
        temporary_context = tempfile.TemporaryDirectory(
            prefix="twrpdtgen-cloud-slice-"
        )
        work_dir = Path(temporary_context.name)

    firmware = work_dir / (
        f"{args.model.strip()}_{args.region.strip()}_firmware.zip"
    )
    try:
        download_firmware(
            args.model,
            args.region,
            firmware,
            version=args.version,
            threads=args.threads,
            samloader=args.samloader,
        )
        result = slice_firmware(
            firmware,
            args.partition,
            output=output,
            package=args.package,
            member=args.member,
            overwrite=args.overwrite,
        )
        _print_result(result)
        if args.keep_firmware:
            print(f"  firmware kept at: {firmware}")
        else:
            firmware.unlink(missing_ok=True)
        if args.colab_download:
            _colab_download(result.output)
    finally:
        if temporary_context is not None:
            temporary_context.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
