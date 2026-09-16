# Adding new reels from your phone

Share a reel from Instagram, type the venue name, done. The site updates itself in about
a minute. No laptop, no server, nothing running in the background.

```
Instagram → Share → "Add to London Map" → type venue name → done
                                                  ↓
                                    GitHub Action geocodes it
                                                  ↓
                                    pins.json updated, site rebuilds
```

## Why it asks you to type the name

Instagram blocks reading captions from outside their app. Anything that tried to scrape
the venue name would fail silently on some reels and you would never know which ones. Five
seconds of typing is more reliable — and you usually give a better search term than the
caption would, because you know what the place is called.

---

## One-time setup

### 1. Create a GitHub token

1. Go to **https://github.com/settings/personal-access-tokens/new**
2. **Token name**: `london-map-shortcut`
3. **Expiration**: 1 year — put a reminder in your calendar, because when it expires the
   shortcut just fails and nothing tells you why
4. **Repository access** → *Only select repositories* → **london-map**
5. **Permissions** → *Repository permissions* → **Contents** → **Read and write**
   (that one permission is all it needs — this is the narrowest token GitHub can issue
   for this job)
6. **Generate token** and copy it. You cannot see it again.

### 2. Build the Shortcut

Open **Shortcuts** → **+** → rename it **Add to London Map**.

Tap the ⓘ (Details) and turn **Show in Share Sheet** ON. Under *Share Sheet Types*, accept
**URLs** and **Text** only — untick everything else so it doesn't clutter other share sheets.

Then add these actions in order:

| # | Action | Set it to |
|---|---|---|
| 1 | **Receive** | *URLs and Text* from *Share Sheet* |
| 2 | **Text** | Paste your token. Nothing else in this box. |
| 3 | **Ask for Input** | Prompt: `Venue name?` · Input type: *Text* |
| 4 | **Get Contents of URL** | See below |
| 5 | **Show Notification** | `Added to the map 🗺️` |

**Action 4 in detail** — tap *Show More*:

- **URL**: `https://api.github.com/repos/Faisal-UX-Portfolio/london-map/dispatches`
- **Method**: `POST`
- **Headers**:
  - `Authorization` → `Bearer ` followed by the **Text** variable from step 2
  - `Accept` → `application/vnd.github+json`
- **Request Body**: `JSON`
  - `event_type` (Text) → `new-venue`
  - `client_payload` (Dictionary):
    - `venue_name` (Text) → the **Provided Input** variable from step 3
    - `reel_url` (Text) → the **Shortcut Input** variable from step 1

### 3. Test it

Open any reel in Instagram → **Share** → **Add to London Map** → type a venue name.

Watch it run at
**https://github.com/Faisal-UX-Portfolio/london-map/actions**.
The site updates about a minute after the run goes green.

You can also test without a phone: Actions → *Add venue from shared reel* → **Run workflow**
→ type a name and a URL.

---

## When something doesn't work

**The shortcut errors immediately.** Usually the token — check it hasn't expired, and that
the `Authorization` header reads `Bearer ghp_...` with a space after `Bearer`.

**The run goes green but no pin appears.** The venue couldn't be matched confidently, so it
went to `data/needs-review.json` rather than risk putting a wrong address on your map. Open
that file to see what it found. Fixing it is usually a matter of adding the venue by hand
with a better name.

**The pin is in the wrong place.** Chains are the usual cause — several branches share a
name and it picked the wrong one. Include the area when you type: `Kricket Soho` rather than
`Kricket`.

## About the token on your phone

It lives as plain text inside the Shortcut, which is unavoidable without running a server.

The realistic risk is **sharing the Shortcut with someone** — iOS makes that one tap, and it
exports the token along with it. Don't share this particular shortcut; if you want to show
someone how it works, clear the token field first.

The token can only write to this one repository. The worst case if it leaked is someone
committing junk to a public list of restaurant pins, which is a one-line revert.
