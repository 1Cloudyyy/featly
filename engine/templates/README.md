# Templates Directory

Place PNG template images here for OpenCV template matching.

## Required Templates

- `trade_request_notification.png` — incoming trade request popup
- `accept_button.png` — accept trade button
- `search_box.png` — search box in trade window
- `your_offer.png` — "Your Offer" area
- `confirm_button.png` — confirm/accept button (gray or green)
- `reconnect_button.png` — reconnect button after disconnect
- `mm2_hud.png` — MM2 HUD element (to confirm in-game)
- `you_have_accepted.png` — "YOU HAVE ACCEPTED" text

## How to Create Templates

1. Take a screenshot of the element in Roblox MM2
2. Crop tightly around the element
3. Save as PNG (lossless)
4. Name it according to the list above
5. Place in this directory

## Tips

- Keep templates small (tight crop = faster matching)
- Use consistent resolution (same as your game window)
- Test with `template_threshold: 0.8` first, adjust if needed
