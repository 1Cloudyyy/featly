# Templates Directory

Place PNG template images here for OpenCV template matching.

## Required Templates

| File | What to crop |
|------|-------------|
| `trade_request_notification.png` | Accept button from trade request popup |
| `search_box.png` | Search input field in trade window |
| `yes_button.png` | Yes button from "ARE YOU SURE?" dialog |
| `you_have_accepted.png` | "YOU HAVE ACCEPTED" text after trade complete |

## Optional Templates

| File | What to crop |
|------|-------------|
| `reconnect_button.png` | Reconnect button after disconnect |
| `mm2_hud.png` | HUD element (confirms in-game) |

## How to Create

1. Open Roblox MM2
2. Trigger the screen (e.g. send yourself a trade request)
3. Take a screenshot (Win+Shift+S)
4. Paste into Paint / any editor
5. Crop tightly around the element
6. Save as PNG → place in this directory

## Tips

- Crop TIGHT — only the button/text, no background
- Use same resolution as your game window
- Test with `template_threshold: 0.8`, lower if not detecting
