"""Ephemeral student profile for admissions counseling (session-scoped, not a User DB)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StudentProfile(BaseModel):
    """Lightweight profile collected during one chat/voice session."""

    score_thpt: float | None = None
    score_dgnl: float | None = None
    subject_combo: str | None = None
    preferred_majors: list[str] = Field(default_factory=list)
    preferred_program: str | None = None  # tieu_chuan | tieng_anh | lien_ket | ...
    budget_note: str | None = None
    admission_method: str | None = None  # thpt | dgnl | hoc_ba | ...
    notes: str | None = None

    def summary_vi(self) -> str:
        parts: list[str] = []
        if self.score_thpt is not None:
            parts.append(f"điểm THPT ~{self.score_thpt}")
        if self.score_dgnl is not None:
            parts.append(f"điểm ĐGNL ~{self.score_dgnl}")
        if self.subject_combo:
            parts.append(f"tổ hợp {self.subject_combo}")
        if self.admission_method:
            parts.append(f"phương thức {self.admission_method}")
        if self.preferred_majors:
            parts.append("quan tâm: " + ", ".join(self.preferred_majors))
        if self.preferred_program:
            parts.append(f"chương trình {self.preferred_program}")
        if self.budget_note:
            parts.append(f"ngân sách: {self.budget_note}")
        if self.notes:
            parts.append(self.notes)
        return "; ".join(parts) if parts else "chưa có thông tin hồ sơ"

    def merge_patch(self, patch: dict) -> StudentProfile:
        data = self.model_dump()
        for key, value in patch.items():
            if value is None or value == "" or value == []:
                continue
            if key == "preferred_majors" and isinstance(value, list):
                merged = list(dict.fromkeys([*(data.get("preferred_majors") or []), *value]))
                data["preferred_majors"] = merged
            elif key in data:
                data[key] = value
        return StudentProfile.model_validate(data)
