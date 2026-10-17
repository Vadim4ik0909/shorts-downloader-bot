from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class MediaItem:
    media_type: str  # 'video', 'photo', 'audio'
    file_path: Path
    caption: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None


@dataclass
class DownloadResult:
    title: str
    items: List[MediaItem] = field(default_factory=list)
    temp_dir: Optional[Path] = None
    source: str = ""
