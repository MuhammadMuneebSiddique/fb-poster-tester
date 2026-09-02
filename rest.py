
import sys
import os
import subprocess
import json
import argparse
from pathlib import Path
from urllib.parse import urlparse


def download_video(url, output_dir=None, format=None, quality=None):
    """Download video using yt-dlp."""
    if output_dir is None:
        output_dir = os.getcwd()

    # Build yt-dlp command
    cmd = ['yt-dlp', url]

    # Set output template
    cmd.extend(['-o', f'{output_dir}/%(title)s.%(ext)s'])

    # Handle format and quality
    if format:
        cmd.extend(['-f', format])
    elif quality:
        # Map quality to format selector
        quality_map = {
            'best': 'best',
            '1080p': 'bestvideo[height<=1080]+bestaudio/best',
            '720p': 'bestvideo[height<=720]+bestaudio/best',
            '480p': 'bestvideo[height<=480]+bestaudio/best',
            'audio': 'bestaudio'
        }
        if quality in quality_map:
            cmd.extend(['-f', quality_map[quality]])

    # Add some useful options
    cmd.extend([
        '--no-playlist',  # Only download single video
        '--write-info-json',  # Save metadata
        '--write-thumbnail'  # Save thumbnail
    ])

    print(f"Downloading video from: {url}", file=sys.stderr)
    print(f"Output directory: {output_dir}", file=sys.stderr)

    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error during download: {e}", file=sys.stderr)
        return False



download_video(url="https://www.tiktok.com/@waffleskkw/video/7678161526284602644",output_dir="./downloads")

