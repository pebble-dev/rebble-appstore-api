import os
import io
import requests

from flask import Flask
from PIL import Image, ImageDraw, ImageFont, ImageChops
from math import ceil

from .utils import valid_platforms

parent_app = None

canvas_size = (780, 520)

background_color=(255, 71, 0)
overlay_color=(55, 58, 60)
text_color=(255, 255, 255)

overlay_box=(0, 392, 780, 520)
icon_position=(24, 416)
base_title_position=(36, 404)
base_author_position=(36, 460)
base_text_space=530
logo_position=(576, 418)

def platform_borders(platform):
    if platform == 'emery':
        return {
            'image': Image.open(os.path.join(parent_app.static_folder, 'emery-border.png')).convert("RGBA"),
            'fallback': Image.open(os.path.join(parent_app.static_folder, 'fallback-emery.png')).convert("RGBA"),
            'offset': (65, 79)
        }

    if platform == 'diorite' or platform == 'flint':
        return {
            'image': Image.open(os.path.join(parent_app.static_folder, 'diorite-border.png')).convert("RGBA"),
            'fallback': Image.open(os.path.join(parent_app.static_folder, 'fallback-bw.png')).convert("RGBA"),
            'offset': (54, 110)
        }

    if platform == 'basalt':
        return {
            'image': Image.open(os.path.join(parent_app.static_folder, 'basalt-border.png')).convert("RGBA"),
            'fallback': Image.open(os.path.join(parent_app.static_folder, 'fallback-basalt.png')).convert("RGBA"),
            'offset': (88,111)
        }

    if platform == 'chalk':
        return {
            'image': Image.open(os.path.join(parent_app.static_folder, 'chalk-border.png')).convert("RGBA"),
            'fallback': Image.open(os.path.join(parent_app.static_folder, 'fallback-chalk.png')).convert("RGBA"),
            'offset': (71,105)
        }

    return {
        'image': Image.open(os.path.join(parent_app.static_folder, 'aplite-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(parent_app.static_folder, 'fallback-bw.png')).convert("RGBA"),
        'offset': (68,106)
    }

def preferred_grouping(platforms):
    order = [['diorite', 'emery'], ['flint', 'emery'], ['basalt', 'emery'], ['chalk', 'emery'],
        ['basalt', 'diorite'], ['basalt', 'flint'], ['basalt', 'chalk'], ['basalt', 'aplite'],
        ['flint'], ['emery'], ['diorite'], ['chalk'], ['basalt'], ['aplite']]
    for selection in order:
      if len(selection) == len(selection & platforms):
        return selection

def load_image_from_url(url, fallback):
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        if fallback:
            return fallback
        raise e

def draw_text_ellipsized(draw, text, font, xy, max_width):
    if draw.textlength(text, font=font) <= max_width:
        draw.text(xy, text, font=font, fill=text_color)
        return

    ellipsis = "…"
    ellipsis_width = draw.textlength(ellipsis, font=font)

    trimmed = ""
    for char in text:
        if draw.textlength(trimmed + char, font=font) + ellipsis_width <= max_width:
            trimmed += char
        else:
            break

    draw.text(xy, trimmed + ellipsis, font=font, fill=text_color)

def platform_image_in_border(canvas, image_url, top_left, platform):
    border = platform_borders(platform)
    img = load_image_from_url(image_url, border['fallback'])

    if platform == 'chalk':
        chalk_mask = Image.open(os.path.join(parent_app.static_folder, 'chalk-mask.png')).convert('L')
        img.putalpha(chalk_mask)

    ix = top_left[0] + border['offset'][0]
    iy = top_left[1] + border['offset'][1]

    canvas.alpha_composite(img, (ix, iy))

    canvas.alpha_composite(border['image'], top_left)

def generate_preview_image(title, developer, icon, screenshots):
    canvas = Image.new("RGBA", canvas_size, background_color)
    draw = ImageDraw.Draw(canvas)

    logo=Image.open(os.path.join(parent_app.static_folder, 'rebble-appstore-logo.png')).convert('RGBA')

    draw.rectangle(overlay_box, fill=overlay_color)
    canvas.alpha_composite(logo, logo_position)

    platforms = preferred_grouping(screenshots.keys())
    start_x = ceil((canvas.width - sum(platform_borders(platform)['image'].width for platform in platforms)) / 2)

    for platform in platforms:
        platform_image_in_border(
            canvas=canvas,
            image_url=screenshots[platform],
            top_left=(start_x, 0),
            platform=platform
        )
        start_x += platform_borders(platform)['image'].width

    title_position = base_title_position
    author_position = base_author_position
    text_space = base_text_space

    icon_image = None
    try:
        icon_image = load_image_from_url(icon, None)
    except Exception as e:
        icon_image = None

    if icon_image:
        icon_mask = Image.open(os.path.join(parent_app.static_folder, 'icon-mask.png')).convert('L')

        icon_image.putalpha(ImageChops.multiply(icon_mask, icon_image.split()[3]))
        canvas.alpha_composite(icon_image, icon_position)
        title_position = (title_position[0] + 88, title_position[1])
        author_position = (author_position[0] + 88, author_position[1])
        text_space -= 88

    font_large = ImageFont.truetype(os.path.join(parent_app.static_folder, 'Lato-Bold.ttf'), 48)
    font_small = ImageFont.truetype(os.path.join(parent_app.static_folder, 'Lato-Regular.ttf'), 32)

    draw_text_ellipsized(draw, title, font_large, title_position, text_space)
    draw_text_ellipsized(draw, developer, font_small, author_position, text_space)

    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()

def init_app(app):
    global parent_app
    parent_app = app
