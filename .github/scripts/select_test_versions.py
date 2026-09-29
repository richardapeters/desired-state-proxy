import argparse
import json
import sys
import urllib.request
from functools import lru_cache

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

REQUEST_TIMEOUT_SECONDS = 30


def is_python_compatible(files, python_version):
    for file in files:
        requires_python = file.get("requires_python")
        if not requires_python or python_version in SpecifierSet(requires_python):
            return True
    return False


def fetch_releases(package_name):
    with urllib.request.urlopen(
        f"https://pypi.org/pypi/{package_name}/json", timeout=REQUEST_TIMEOUT_SECONDS
    ) as response:
        return json.load(response)["releases"]


def marker_environment_for(python_version):
    environment = default_environment()
    environment["python_version"] = f"{python_version.major}.{python_version.minor}"
    environment["python_full_version"] = ".".join(
        str(part) for part in (python_version.release + (0, 0))[:3]
    )
    return environment


def find_supported_versions(channel, target_python):
    helper_package = "pytest-homeassistant-custom-component"
    python_version = Version(target_python)
    requirement_environment = marker_environment_for(python_version)
    homeassistant_releases = fetch_releases("homeassistant")
    helper_releases = fetch_releases(helper_package)

    want_prerelease = channel == "preview"
    homeassistant_versions = sorted(
        (
            Version(version)
            for version, files in homeassistant_releases.items()
            if files
            and is_python_compatible(files, python_version)
            and Version(version).is_prerelease is want_prerelease
        ),
        reverse=True,
    )
    if not homeassistant_versions:
        raise RuntimeError(
            f"No {channel} Home Assistant release available for Python {python_version}"
        )

    helper_versions = sorted(
        (
            Version(version)
            for version, files in helper_releases.items()
            if files and not Version(version).is_prerelease and Version(version) >= Version("0.13.0")
        ),
        reverse=True,
    )

    @lru_cache(maxsize=None)
    def helper_homeassistant_specifier(helper_version):
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{helper_package}/{helper_version}/json",
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            requires_dist = json.load(response)["info"].get("requires_dist") or []

        for requirement_text in requires_dist:
            requirement = Requirement(requirement_text)
            if requirement.name != "homeassistant":
                continue
            if requirement.marker and not requirement.marker.evaluate(requirement_environment):
                continue
            return requirement.specifier
        return None

    for homeassistant_version in homeassistant_versions:
        for helper_version in helper_versions:
            requirement_specifier = helper_homeassistant_specifier(str(helper_version))
            if requirement_specifier and homeassistant_version in requirement_specifier:
                print(homeassistant_version, helper_version)
                return

    raise RuntimeError(
        f"No {channel} Home Assistant version found for {helper_package}>=0.13.0 on Python {python_version}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("channel", choices=("stable", "preview"))
    parser.add_argument("target_python")
    args = parser.parse_args()
    find_supported_versions(args.channel, args.target_python)
