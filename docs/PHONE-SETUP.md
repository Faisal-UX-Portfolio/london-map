# Putting this on your iPhone

## Install it to the home screen

1. Open **https://faisal-ux-portfolio.github.io/london-map/** in **Safari**
   (it must be Safari — Chrome on iOS cannot add to the home screen).
2. Tap the **Share** button.
3. Scroll down, tap **Add to Home Screen**, then **Add**.

You now have a "London" icon. Opening it runs the app full-screen with no Safari chrome,
its own icon, and a translucent status bar — it behaves like a native app.

## The first time you tap "Near me"

iOS asks permission for location. Allow it. If you tap **Don't Allow** by accident, the
app will tell you it's blocked — to fix it:

**Settings → Apps → Safari → Location** → set to *Ask* or *While Using*.

Location only ever runs in your browser. Nothing leaves the device — there is no server
to send it to.

## Using it offline

Once you've opened the app while online, it keeps working without a signal: your places,
search, filters and every reel link stay available. **Map tiles do not cache** — the
background will be blank underground, but pins and details still work. That's a
deliberate call: caching tiles for 270+ venues across London would be a large download
and goes against OpenStreetMap's usage policy.

## When new places are added

The app checks for fresh data every time you open it and falls back to the last copy it
saw if you're offline. Nothing to refresh manually.
