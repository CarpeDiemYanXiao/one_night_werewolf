from PIL import Image, ImageDraw, ImageFont
import os

roles = [
    "狼人","预言家","强盗","捣蛋鬼","酒鬼","失眠者","村民",
    "化身幽灵","皮匠","猎人","爪牙"
]

out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "roles")
os.makedirs(out_dir, exist_ok=True)

# 使用系统默认字体；在 Windows 上通常能找到微软雅黑或 Arial
try:
    font = ImageFont.truetype("msyh.ttf", 36)
except Exception:
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()

for role in roles:
    img = Image.new("RGBA", (300, 420), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    # 背景色
    draw.rectangle([(0,0),(300,420)], fill=(240,240,240))
    # 中央写角色名
    w, h = draw.textsize(role, font=font)
    draw.text(((300-w)/2, (420-h)/2), role, fill=(40,40,40), font=font)
    # 边框
    draw.rectangle([(5,5),(295,415)], outline=(100,100,100), width=4)
    path = os.path.join(out_dir, f"{role}.png")
    img.save(path)
    print("生成：", path)

print("占位图片生成完成，共生成", len(roles), "张")
