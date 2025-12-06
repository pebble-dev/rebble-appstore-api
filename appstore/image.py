import os
import io

from flask import Flask
from PIL import Image, ImageDraw, ImageFont, ImageChops
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil

from .s3 import download_asset
from .utils import valid_platforms, plat_dimensions

parent_app = None

static_folder = os.path.join(os.path.dirname(__file__), 'static')

background = Image.open(os.path.join(static_folder, 'background.png')).convert('RGBA')

text_color=(255, 255, 255)

overlay_box=(0, 392, 780, 520)
icon_position=(24, 416)
base_title_position=(36, 404)
base_author_position=(36, 460)
base_text_space=530

icon_mask = Image.open(os.path.join(static_folder, 'icon-mask.png')).convert('L')
chalk_mask = Image.open(os.path.join(static_folder, 'chalk-mask.png')).convert('L')

platform_borders = {
    'aplite': {
        'image': Image.open(os.path.join(static_folder, 'aplite-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(static_folder, 'fallback-bw.png')).convert("RGBA"),
        'offset': (68,106)
    },
    'basalt': {
        'image': Image.open(os.path.join(static_folder, 'basalt-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(static_folder, 'fallback-basalt.png')).convert("RGBA"),
        'offset': (88,111)
    },
    'chalk': {
        'image': Image.open(os.path.join(static_folder, 'chalk-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(static_folder, 'fallback-chalk.png')).convert("RGBA"),
        'offset': (71,105)
    },
    'diorite': {
        'image': Image.open(os.path.join(static_folder, 'diorite-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(static_folder, 'fallback-bw.png')).convert("RGBA"),
        'offset': (54, 110)
    },
    'emery': {
        'image': Image.open(os.path.join(static_folder, 'emery-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(static_folder, 'fallback-emery.png')).convert("RGBA"),
        'offset': (65, 79)
    },
    'flint': {
        'image': Image.open(os.path.join(static_folder, 'diorite-border.png')).convert("RGBA"),
        'fallback': Image.open(os.path.join(static_folder, 'fallback-bw.png')).convert("RGBA"),
        'offset': (54, 110)
    }
}

font_large = ImageFont.truetype(os.path.join(static_folder, 'Lato-Bold.ttf'), 48)
font_small = ImageFont.truetype(os.path.join(static_folder, 'Lato-Regular.ttf'), 32)

def preferred_grouping(platforms):
    order = [['diorite', 'emery'], ['flint', 'emery'], ['basalt', 'emery'], ['chalk', 'emery'],
        ['basalt', 'diorite'], ['basalt', 'flint'], ['basalt', 'chalk'], ['basalt', 'aplite'],
        ['flint'], ['emery'], ['diorite'], ['chalk'], ['basalt'], ['aplite']]
    for selection in order:
      if len(selection) == len(selection & platforms):
        return selection

def load_image_from_id(id, fallback):
    try:
        file = io.BytesIO()
        download_asset(id, file)
        return Image.open(file).convert("RGBA")
    except Exception as e:
        if fallback:
            return fallback
        raise e

def load_images_parallel(ids_with_fallbacks):
    output = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_key = {
            executor.submit(load_image_from_id, id, fallback): key
            for key, (id, fallback) in ids_with_fallbacks.items()
        }

        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                output[key] = future.result()
            except Exception as e:
                output[key] = None

    return output

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

def platform_image_in_border(canvas, image, top_left, platform):
    border = platform_borders[platform]
    image = image.resize(plat_dimensions[platform], resample=Image.NEAREST)

    if platform == 'chalk':
        image.putalpha(chalk_mask)

    ix = top_left[0] + border['offset'][0]
    iy = top_left[1] + border['offset'][1]

    canvas.alpha_composite(image, (ix, iy))

    canvas.alpha_composite(border['image'], top_left)

def generate_preview_image(title, developer, icon, screenshots):
    canvas = background.copy()
    draw = ImageDraw.Draw(canvas)

    platforms = preferred_grouping(screenshots.keys())
    start_x = ceil((canvas.width - sum(platform_borders[platform]['image'].width for platform in platforms)) / 2)

    image_ids = {}

    if icon:
        image_ids['icon'] = (icon, None)

    for platform in platforms:
        image_ids[platform] = (screenshots[platform], platform_borders[platform]['fallback'])

    loaded_images = load_images_parallel(image_ids)

    for platform in platforms:
        platform_image_in_border(
            canvas=canvas,
            image=loaded_images[platform],
            top_left=(start_x, 0),
            platform=platform
        )
        start_x += platform_borders[platform]['image'].width

    title_position = base_title_position
    author_position = base_author_position
    text_space = base_text_space

    icon_image = loaded_images['icon'] if 'icon' in loaded_images else None

    if icon_image:
        icon_image = icon_image.resize((80,80))
        icon_image.putalpha(ImageChops.multiply(icon_mask, icon_image.split()[3]))
        canvas.alpha_composite(icon_image, icon_position)
        title_position = (title_position[0] + 88, title_position[1])
        author_position = (author_position[0] + 88, author_position[1])
        text_space -= 88

    draw_text_ellipsized(draw, title, font_large, title_position, text_space)
    draw_text_ellipsized(draw, developer, font_small, author_position, text_space)

    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()

def init_app(app):
    global parent_app
    parent_app = app
