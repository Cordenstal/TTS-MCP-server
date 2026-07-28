"""Draw a friendly cat with Python's standard-library turtle module.

Run with::

    python draw_cat.py
"""

from __future__ import annotations

import turtle


OUTLINE = "#263238"
FUR = "#f4a261"
FUR_DARK = "#d9783f"
CREAM = "#ffe0b2"


def make_pen() -> turtle.Turtle:
    pen = turtle.Turtle(visible=False)
    pen.speed(0)
    pen.pensize(4)
    return pen


def circle(pen: turtle.Turtle, x: float, y: float, radius: float, fill: str) -> None:
    pen.penup()
    pen.goto(x, y - radius)
    pen.setheading(0)
    pen.color(OUTLINE, fill)
    pen.pendown()
    pen.begin_fill()
    pen.circle(radius)
    pen.end_fill()


def ellipse(
    pen: turtle.Turtle,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    heading: float = 0,
) -> None:
    pen.penup()
    pen.goto(x, y)
    pen.setheading(heading)
    pen.color(OUTLINE, fill)
    pen.pendown()
    pen.begin_fill()
    for _ in range(2):
        pen.circle(width / 2, 90)
        pen.circle(height / 2, 90)
    pen.end_fill()


def polygon(pen: turtle.Turtle, points: tuple[tuple[float, float], ...], fill: str) -> None:
    pen.penup()
    pen.goto(*points[0])
    pen.color(OUTLINE, fill)
    pen.pendown()
    pen.begin_fill()
    for point in points[1:]:
        pen.goto(*point)
    pen.goto(*points[0])
    pen.end_fill()


def line(pen: turtle.Turtle, points: tuple[tuple[float, float], ...], color: str = OUTLINE, width: int = 4) -> None:
    pen.penup()
    pen.goto(*points[0])
    pen.color(color)
    pen.pensize(width)
    pen.pendown()
    for point in points[1:]:
        pen.goto(*point)
    pen.penup()
    pen.pensize(4)


def draw_cat(pen: turtle.Turtle) -> None:
    # Tail behind the body.
    line(pen, ((-75, -55), (-145, -5), (-155, 75), (-120, 108)), FUR_DARK, 18)
    line(pen, ((-75, -55), (-145, -5), (-155, 75), (-120, 108)), OUTLINE, 4)

    # Body and belly.
    ellipse(pen, -15, -18, 150, 205, FUR, 82)
    ellipse(pen, 2, -35, 82, 125, CREAM, 82)

    # Paws resting on the ground.
    ellipse(pen, -55, -110, 48, 82, FUR, 82)
    ellipse(pen, 35, -110, 48, 82, FUR, 82)
    line(pen, ((-58, -113), (-48, -113)), FUR_DARK, 3)
    line(pen, ((32, -113), (42, -113)), FUR_DARK, 3)

    # Head, ears, and inner ears.
    circle(pen, 4, 135, 78, FUR)
    polygon(pen, ((-60, 178), (-48, 258), (8, 205)), FUR)
    polygon(pen, ((48, 205), (103, 258), (110, 170)), FUR)
    polygon(pen, ((-42, 200), (-47, 237), (-16, 207)), "#e76f51")
    polygon(pen, ((62, 207), (96, 237), (91, 187)), "#e76f51")

    # Eyes, muzzle, nose, and smile.
    circle(pen, -24, 151, 12, "#ffffff")
    circle(pen, 40, 151, 12, "#ffffff")
    circle(pen, -22, 151, 5, "#3a86ff")
    circle(pen, 38, 151, 5, "#3a86ff")
    ellipse(pen, 7, 113, 56, 38, CREAM, 0)
    polygon(pen, ((-5, 121), (7, 111), (19, 121), (7, 130)), "#e76f51")
    line(pen, ((7, 111), (7, 98), (-5, 91)), OUTLINE, 3)
    line(pen, ((7, 98), (19, 91)), OUTLINE, 3)

    # Whiskers.
    line(pen, ((-13, 119), (-95, 132)), OUTLINE, 2)
    line(pen, ((-13, 108), (-100, 105)), OUTLINE, 2)
    line(pen, ((27, 119), (105, 132)), OUTLINE, 2)
    line(pen, ((27, 108), (110, 104)), OUTLINE, 2)


def draw_scene() -> None:
    screen = turtle.Screen()
    screen.setup(width=800, height=650)
    screen.title("A Friendly Cat")
    screen.bgcolor("#bde0fe")
    pen = make_pen()

    # Simple background and ground.
    circle(pen, -300, 230, 42, "#ffd166")
    ellipse(pen, 0, -178, 850, 125, "#90be6d")
    line(pen, ((-400, -145), (400, -145)), "#588157", 4)

    draw_cat(pen)

    pen.goto(0, 295)
    pen.color(OUTLINE)
    pen.write("Hello, cat!", align="center", font=("Arial", 22, "bold"))
    screen.exitonclick()


if __name__ == "__main__":
    draw_scene()
