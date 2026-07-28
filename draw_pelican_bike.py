"""Draw a cheerful pelican riding a bicycle with Python's standard library.

Run with::

    python draw_pelican_bike.py
"""

from __future__ import annotations

import turtle
import math


def setup_pen() -> turtle.Turtle:
    pen = turtle.Turtle(visible=False)
    pen.speed(0)
    pen.pensize(4)
    pen.color("#263238")
    return pen


def filled_circle(pen: turtle.Turtle, x: float, y: float, radius: float, color: str) -> None:
    pen.penup()
    pen.goto(x, y - radius)
    pen.setheading(0)
    pen.color("#263238", color)
    pen.pendown()
    pen.begin_fill()
    pen.circle(radius)
    pen.end_fill()


def filled_ellipse(
    pen: turtle.Turtle,
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
    angle: float = 0,
) -> None:
    pen.penup()
    pen.goto(x, y)
    pen.setheading(angle)
    pen.color("#263238", color)
    pen.pendown()
    pen.begin_fill()
    for _ in range(2):
        pen.circle(width / 2, 90)
        pen.circle(height / 2, 90)
    pen.end_fill()


def line(pen: turtle.Turtle, points: tuple[tuple[float, float], ...], color: str, width: int = 4) -> None:
    pen.penup()
    pen.goto(*points[0])
    pen.color(color)
    pen.pensize(width)
    pen.pendown()
    for point in points[1:]:
        pen.goto(*point)
    pen.penup()
    pen.pensize(4)


def draw_bicycle(pen: turtle.Turtle) -> None:
    rear_wheel = (-145, -115)
    front_wheel = (145, -115)
    wheel_radius = 58

    for wheel in (rear_wheel, front_wheel):
        filled_circle(pen, *wheel, wheel_radius, "#f8fafc")
        filled_circle(pen, *wheel, 7, "#90a4ae")
        for spoke_angle in range(0, 360, 45):
            pen.setheading(spoke_angle)
            line(
                pen,
                (wheel, (wheel[0] + wheel_radius * math.cos(math.radians(spoke_angle)),
                         wheel[1] + wheel_radius * math.sin(math.radians(spoke_angle)))),
                "#b0bec5",
                1,
            )

    rear_hub = rear_wheel
    front_hub = front_wheel
    crank = (-10, -110)
    seat_post = (-45, 5)
    handle_post = (92, -5)
    frame_color = "#e4572e"

    line(pen, (rear_hub, seat_post, crank, rear_hub), frame_color, 7)
    line(pen, (seat_post, handle_post, crank, seat_post), frame_color, 7)
    line(pen, (handle_post, front_hub), frame_color, 7)
    line(pen, ((-65, 8), (-25, 8)), "#263238", 7)
    line(pen, (handle_post, (112, 25), (128, 20)), "#263238", 5)

    filled_circle(pen, *crank, 8, "#ffd166")
    line(pen, (crank, (18, -92)), "#263238", 4)
    line(pen, ((18, -92), (31, -92)), "#263238", 5)


def draw_pelican(pen: turtle.Turtle) -> None:
    # Body and tail.
    filled_ellipse(pen, -20, 35, 108, 145, "#f5f7f8", 82)
    filled_ellipse(pen, -70, 36, 58, 82, "#c7d1d6", 125)
    filled_ellipse(pen, -62, 74, 64, 112, "#b0bec5", 25)

    # Neck, head, eye, and the pelican's unmistakable pouchy bill.
    filled_ellipse(pen, 42, 115, 50, 82, "#f5f7f8", 10)
    filled_circle(pen, 65, 165, 38, "#f5f7f8")
    filled_ellipse(pen, 112, 148, 112, 36, "#f4a261", -8)
    filled_ellipse(pen, 118, 140, 103, 25, "#e8894a", -8)
    filled_circle(pen, 77, 176, 7, "#263238")
    filled_circle(pen, 79, 179, 2, "#ffffff")

    # Wing holding the handlebars.
    filled_ellipse(pen, 20, 65, 48, 122, "#dbe3e7", 35)
    line(pen, ((39, 72), (90, 31)), "#90a4ae", 3)

    # Legs reaching the pedals.
    line(pen, ((-2, -8), (-4, -63), (18, -92)), "#f4a261", 8)
    line(pen, ((20, -5), (31, -50), (18, -92)), "#f4a261", 8)
    line(pen, ((18, -92), (35, -92)), "#e8894a", 5)
    line(pen, ((-5, -64), (-22, -70)), "#e8894a", 5)


def draw_scene() -> None:
    screen = turtle.Screen()
    screen.setup(width=900, height=650)
    screen.title("Pelican on a Bicycle")
    screen.bgcolor("#bde0fe")

    pen = setup_pen()

    # Sun, clouds, and road.
    filled_circle(pen, -345, 225, 42, "#ffd166")
    filled_circle(pen, -245, 225, 20, "#ffffff")
    filled_circle(pen, -220, 233, 28, "#ffffff")
    filled_circle(pen, -190, 225, 19, "#ffffff")
    line(pen, ((-450, -175), (450, -175)), "#607d8b", 5)
    for x in range(-420, 421, 100):
        line(pen, ((x, -215), (x + 55, -215)), "#ffffff", 7)

    draw_bicycle(pen)
    draw_pelican(pen)

    # A little motion in the scene.
    line(pen, ((-330, 10), (-280, 10)), "#ffffff", 5)
    line(pen, ((-355, -15), (-320, -15)), "#ffffff", 5)
    pen.penup()
    pen.goto(0, 260)
    pen.color("#263238")
    pen.write("Pedal, pelican, pedal!", align="center", font=("Arial", 20, "bold"))

    screen.exitonclick()


if __name__ == "__main__":
    draw_scene()
