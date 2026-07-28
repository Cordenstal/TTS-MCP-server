"""Draw a cheerful pelican riding a bicycle with Python's turtle module.

Run with:

    python docs/examples/pelican_bike.py
"""

from __future__ import annotations

import math
import turtle
from collections.abc import Iterable


Point = tuple[float, float]


def polygon(pen: turtle.Turtle, points: Iterable[Point], fill: str, outline: str = "") -> None:
    """Draw a filled polygon from a sequence of (x, y) points."""
    points = list(points)
    pen.color(outline or fill)
    pen.fillcolor(fill)
    pen.penup()
    pen.goto(*points[0])
    pen.pendown()
    pen.begin_fill()
    for point in points[1:]:
        pen.goto(*point)
    pen.goto(*points[0])
    pen.end_fill()
    pen.penup()


def line(pen: turtle.Turtle, points: Iterable[Point], color: str, width: int = 4) -> None:
    """Draw a connected line through a sequence of points."""
    points = list(points)
    pen.color(color)
    pen.width(width)
    pen.penup()
    pen.goto(*points[0])
    pen.pendown()
    for point in points[1:]:
        pen.goto(*point)
    pen.penup()


def ellipse(
    pen: turtle.Turtle,
    center: Point,
    radius_x: float,
    radius_y: float,
    fill: str,
    outline: str = "",
) -> None:
    """Approximate an ellipse with a smooth filled polygon."""
    cx, cy = center
    points = [
        (
            cx + radius_x * math.cos(math.radians(angle)),
            cy + radius_y * math.sin(math.radians(angle)),
        )
        for angle in range(0, 360, 6)
    ]
    polygon(pen, points, fill, outline)


def circle(pen: turtle.Turtle, center: Point, radius: float, fill: str, outline: str = "") -> None:
    ellipse(pen, center, radius, radius, fill, outline)


def draw_scenery(pen: turtle.Turtle) -> None:
    """Draw the sky, ground, clouds, sun, and roadside flowers."""
    pen.hideturtle()

    pen.color("#8bd7f5")
    pen.fillcolor("#8bd7f5")
    pen.penup()
    pen.goto(-450, -325)
    pen.pendown()
    pen.begin_fill()
    for point in [(-450, 325), (450, 325), (450, -325)]:
        pen.goto(*point)
    pen.goto(-450, -325)
    pen.end_fill()

    # Rolling grass and a path.
    polygon(pen, [(-450, -180), (450, -125), (450, -325), (-450, -325)], "#9bd36a")
    polygon(pen, [(-450, -250), (450, -195), (450, -240), (-450, -295)], "#e8c989")

    circle(pen, (325, 225), 48, "#ffd45c", "#f5a623")
    ellipse(pen, (-280, 220), 65, 25, "white")
    ellipse(pen, (-215, 232), 50, 20, "white")
    ellipse(pen, (80, 270), 58, 22, "white")
    ellipse(pen, (140, 282), 43, 18, "white")

    # Small flowers beside the path.
    for x, y, color in [(-390, -165, "#ef6b78"), (-350, -173, "#a879e8"), (385, -115, "#ef6b78")]:
        line(pen, [(x, y), (x, y - 30)], "#438b4b", 3)
        for dx, dy in [(-7, 0), (7, 0), (0, -7), (0, 7)]:
            circle(pen, (x + dx, y + dy), 5, color)
        circle(pen, (x, y), 3, "#ffd45c")


def draw_bicycle(pen: turtle.Turtle) -> None:
    """Draw the bicycle underneath the pelican."""
    wheel_color = "#303b4a"
    metal = "#d84f55"
    wheel_centers = [(-120, -155), (180, -155)]

    for center in wheel_centers:
        circle(pen, center, 62, "#f5f7fa", wheel_color)
        circle(pen, center, 7, metal)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            line(
                pen,
                [center, (center[0] + 55 * math.cos(radians), center[1] + 55 * math.sin(radians))],
                "#a8b3bf",
                2,
            )

    rear, front = wheel_centers
    crank = (35, -155)
    seat_post = (-15, -65)
    handle_post = (125, -68)
    line(pen, [rear, seat_post, crank, rear], metal, 7)
    line(pen, [crank, handle_post, front, crank], metal, 7)
    line(pen, [seat_post, handle_post], metal, 7)
    line(pen, [(-45, -58), (15, -58)], wheel_color, 7)
    line(pen, [handle_post, (145, -45)], metal, 6)
    line(pen, [(138, -45), (160, -45)], wheel_color, 5)
    circle(pen, crank, 10, "#ffd45c", wheel_color)
    line(pen, [(35, -155), (52, -135)], wheel_color, 4)
    line(pen, [(35, -155), (18, -174)], wheel_color, 4)


def draw_pelican(pen: turtle.Turtle) -> None:
    """Draw the pelican, including its beak, wing, feet, and helmet."""
    ink = "#34404d"
    white = "#fffaf0"
    cream = "#f0e6d2"
    orange = "#f29b45"

    # Body and tail.
    ellipse(pen, (20, 35), 88, 122, white, ink)
    polygon(pen, [(-45, -15), (-125, -35), (-65, 20)], cream, ink)
    ellipse(pen, (-2, 20), 52, 92, "#dfe7eb", ink)  # folded wing
    line(pen, [(-25, 20), (32, -35), (48, -48)], "#aab8c1", 4)

    # Long neck and head.
    ellipse(pen, (-20, 155), 42, 76, white, ink)
    circle(pen, (-12, 225), 55, white, ink)
    polygon(pen, [(-43, 257), (-125, 238), (-158, 220), (-112, 204), (-28, 215)], orange, ink)
    polygon(pen, [(-125, 238), (-158, 220), (-112, 204), (-76, 221)], "#e87d39", ink)
    circle(pen, (8, 238), 8, "#25313c")
    circle(pen, (10, 241), 3, "white")

    # Helmet and strap.
    ellipse(pen, (-15, 273), 48, 17, "#4c9bd1", ink)
    ellipse(pen, (-15, 286), 38, 20, "#4c9bd1", ink)
    line(pen, [(-47, 280), (-45, 235)], "#3475a5", 4)

    # Feet reaching the pedals.
    line(pen, [(-5, -55), (18, -105), (35, -140)], orange, 8)
    line(pen, [(43, -50), (55, -98), (50, -135)], orange, 8)
    line(pen, [(31, -140), (51, -140)], orange, 6)
    line(pen, [(47, -135), (65, -129)], orange, 6)


def draw() -> None:
    screen = turtle.Screen()
    screen.setup(width=900, height=650)
    screen.title("Pelican on a Bicycle")
    screen.bgcolor("#8bd7f5")
    screen.tracer(False)

    pen = turtle.Turtle(visible=False)
    pen.speed(0)
    pen.pensize(3)

    draw_scenery(pen)
    draw_bicycle(pen)
    draw_pelican(pen)

    screen.update()
    screen.mainloop()


if __name__ == "__main__":
    draw()
