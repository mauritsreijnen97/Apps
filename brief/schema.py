"""The JSON contract between Claude and the renderer.

Claude only ever returns data that matches `BriefContent`. Python turns it into
markup, so the model never writes HTML.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EM_DASH = "—"


class WeatherMotif(str, Enum):
    clear = "clear"                  # mild clear day: full sun, birds, no clouds
    partly_cloudy = "partly_cloudy"  # sun with one passing cloud
    overcast = "overcast"            # dimmed sun, dry clouds
    showers = "showers"              # rain clouds only over the wet parts of the day
    rain = "rain"                    # all-day rain: rain clouds, ripples, dimmed sun
    snow = "snow"
    fog = "fog"


class SectionKind(str, Enum):
    coming_up = "coming_up"
    worth_knowing = "worth_knowing"
    formula1 = "formula1"
    next_week = "next_week"


SECTION_TITLES = {
    SectionKind.coming_up: "Coming up today",
    SectionKind.worth_knowing: "Worth knowing",
    SectionKind.formula1: "Formula 1",
    SectionKind.next_week: "Next week",
}
SECTION_ORDER = [SectionKind.coming_up, SectionKind.worth_knowing, SectionKind.formula1, SectionKind.next_week]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Item(_Strict):
    title: str = Field(description="Short bold headline for the item, plain text, no trailing period.")
    url: str = Field(description="Source URL taken from the web search results. Must be a real article.")
    text: str = Field(description="One or two sentences. Must contain link_phrase word for word.")
    link_phrase: str = Field(description="A few words copied exactly from text; they become the link.")

    @field_validator("url")
    @classmethod
    def _http(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("https://", "http://")):
            raise ValueError("url must be absolute http(s)")
        return v

    @model_validator(mode="after")
    def _phrase_in_text(self) -> "Item":
        if not self.link_phrase.strip():
            raise ValueError("link_phrase is empty")
        if self.link_phrase not in self.text:
            raise ValueError(f"link_phrase {self.link_phrase!r} is not in text")
        return self


class Section(_Strict):
    kind: SectionKind
    items: list[Item]


class Act(_Strict):
    text: str = Field(description="One specific sentence for this part of the day.")


class Mark(_Strict):
    hour: float = Field(description="Paris time as decimal hours, for example 14.5 for 2:30 PM. Between 7 and 23.")
    label: str = Field(description="Two to four words plus the time, for example 'march, 2 PM'.")

    @field_validator("hour")
    @classmethod
    def _range(cls, v: float) -> float:
        if not 5 <= v <= 23.5:
            raise ValueError("hour must be within the day shown (5 to 23.5)")
        return v

    @field_validator("label")
    @classmethod
    def _short(cls, v: str) -> str:
        if len(v) > 28:
            raise ValueError("mark label longer than 28 characters")
        return v


class BriefContent(_Strict):
    headline: str = Field(description="One line, addresses Maurits by name.")
    acts: list[Act] = Field(description="Exactly three: morning from sunrise, midday, evening from sunset.")
    marks: list[Mark] = Field(description="0 to 3 real timed events today, in time order.")
    weather_motif: WeatherMotif
    weather_line: str = Field(description="One sentence on today's weather in Saint-Cloud and Issy.")
    sections: list[Section]

    @model_validator(mode="after")
    def _shape(self) -> "BriefContent":
        if len(self.acts) != 3:
            raise ValueError("acts must have exactly three entries")
        if len(self.marks) > 3:
            raise ValueError("at most three marks")
        if "Maurits" not in self.headline:
            raise ValueError("headline must address Maurits")
        kinds = [s.kind for s in self.sections]
        if len(kinds) != len(set(kinds)):
            raise ValueError("each section kind may appear once")
        if SectionKind.formula1 in kinds and SectionKind.next_week in kinds:
            raise ValueError("formula1 and next_week are alternatives, not both")
        for s in self.sections:
            if s.kind == SectionKind.worth_knowing and not 4 <= len(s.items) <= 6:
                raise ValueError("worth_knowing needs 4 to 6 items")
            if s.kind == SectionKind.formula1 and len(s.items) != 1:
                raise ValueError("formula1 is a single item")
            if not s.items:
                raise ValueError(f"section {s.kind.value} is empty; drop it instead")
        return self

    def all_text(self) -> str:
        parts = [self.headline, self.weather_line, *(a.text for a in self.acts), *(m.label for m in self.marks)]
        for s in self.sections:
            for i in s.items:
                parts += [i.title, i.text]
        return "\n".join(parts)

    def urls(self) -> list[str]:
        return [i.url for s in self.sections for i in s.items]


Hour = Annotated[float, Field(ge=0, le=24)]
Condition = Literal["clear", "partly_cloudy", "overcast", "showers", "rain", "snow", "fog", "unknown"]
