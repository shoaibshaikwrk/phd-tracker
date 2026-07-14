/**
 * Cloud Function relay for AI CV / research-statement tailoring.
 *
 * Why this exists: OpenAI's API does not send CORS headers, so a browser
 * cannot call api.openai.com directly from the website — the request would
 * be blocked by the browser itself before it even reaches OpenAI. This tiny
 * function just forwards the request server-side and streams the response
 * back. It does NOT store the API key or CV text anywhere — both are passed
 * in on each request and only ever held in memory for the duration of that
 * one request.
 *
 * Deploy with: firebase deploy --only functions
 * Requires the Firebase project to be on the Blaze (pay-as-you-go) plan —
 * Cloud Functions cannot run on the free Spark plan. You are only billed for
 * OpenAI usage (via your own OpenAI account/key) and negligible Cloud
 * Functions invocation costs — see "Set up AI tailoring" in DEPLOY.md.
 */

const { onRequest } = require("firebase-functions/v2/https");
const cors = require("cors")({ origin: true });

const OPENAI_URL = "https://api.openai.com/v1/chat/completions";

exports.tailorApplication = onRequest(
  { region: "us-central1", cors: true, memory: "256MiB", timeoutSeconds: 60 },
  (req, res) => {
    cors(req, res, async () => {
      if (req.method !== "POST") {
        res.status(405).json({ error: "Use POST." });
        return;
      }

      const { apiKey, resumeText, position } = req.body || {};

      if (!apiKey || typeof apiKey !== "string" || !apiKey.startsWith("sk-")) {
        res.status(400).json({ error: "Missing or invalid OpenAI API key." });
        return;
      }
      if (!resumeText || typeof resumeText !== "string") {
        res.status(400).json({ error: "Missing CV / research-statement text." });
        return;
      }
      if (!position || !position.title) {
        res.status(400).json({ error: "Missing program details." });
        return;
      }

      const prompt = [
        "You are an expert academic-application editor. Rewrite the CV / research",
        "statement below so it is tightly tailored to the specific PhD program,",
        "lab, or advisor listed, while staying 100% truthful to the candidate's",
        "real experience — never invent employers, titles, dates, degrees,",
        "publications, or skills that are not already present in the original.",
        "You MAY: reorder sections, rephrase to foreground the most relevant",
        "existing experience/projects, connect the candidate's applied/industry",
        "work to a plausible research question for this program, and tighten a",
        "summary or opening paragraph to mirror the program's or advisor's",
        "language and stated research interests.",
        "You MUST NOT: fabricate research experience, publications, or change",
        "facts (employers, dates, degrees, publications).",
        "",
        `Program / position: ${position.title}`,
        `Institution / lab: ${position.company || "Unknown"}`,
        `Location: ${position.location || "Unknown"}`,
        `Source: ${position.source || "Unknown"}`,
        "",
        "Note: only the program title/institution/location are available here",
        "(no full program description was scraped), so tailor based on what",
        "this program or lab is generally known for, while staying grounded in",
        "the candidate's real content below.",
        "",
        "Original CV / research-statement text:",
        "---",
        resumeText,
        "---",
        "",
        "Output ONLY the rewritten text (plain text, no commentary, no markdown",
        "formatting, no explanation before or after).",
      ].join("\n");

      try {
        const openaiResp = await fetch(OPENAI_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model: "gpt-4o-mini",
            messages: [{ role: "user", content: prompt }],
            temperature: 0.4,
          }),
        });

        const data = await openaiResp.json();

        if (!openaiResp.ok) {
          const message = (data && data.error && data.error.message) || `OpenAI error (HTTP ${openaiResp.status})`;
          res.status(openaiResp.status).json({ error: message });
          return;
        }

        const tailoredText = data.choices && data.choices[0] && data.choices[0].message
          ? data.choices[0].message.content
          : "";

        res.status(200).json({ tailoredText });
      } catch (err) {
        res.status(500).json({ error: "Server error calling OpenAI: " + err.message });
      }
    });
  }
);
