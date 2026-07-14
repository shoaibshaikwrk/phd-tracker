// Firebase web app config — this is NOT a secret (Firebase web configs are meant
// to be public; access is controlled by Firestore security rules and the
// "Authorized domains" list in Firebase Auth, not by hiding this file).
//
// This file is committed once and edited by hand — phd_checker.py never
// touches it, so it survives every daily automated regeneration of index.html.
//
// IMPORTANT: these are placeholder values. This tracker is a NEW project —
// it does not reuse the Firebase project from the job-checker site it was
// adapted from. Create your own free Firebase project before deploying:
//   1. https://console.firebase.google.com -> Add project (free "Spark" plan is fine
//      for everything except AI tailoring, which needs "Blaze" — see DEPLOY.md).
//   2. Project settings (gear icon) -> General -> "Your apps" -> Add app -> Web (</>)
//   3. Copy the firebaseConfig object it gives you and paste the values below.
//   4. Enable: Authentication -> Sign-in method -> Email/Password ->
//      turn on "Email link (passwordless sign-in)".
//   5. Enable: Firestore Database -> Create database (production mode is fine;
//      the app only ever reads/writes the position_status and user_resumes
//      collections shown in phd_checker.py / index.html).
//   6. Add phd.placeonus.com (and your github.io URL, for testing) under
//      Authentication -> Settings -> Authorized domains.

const firebaseConfig = {
  apiKey: "REPLACE_ME",
  authDomain: "REPLACE_ME.firebaseapp.com",
  projectId: "REPLACE_ME",
  storageBucket: "REPLACE_ME.firebasestorage.app",
  messagingSenderId: "REPLACE_ME",
  appId: "REPLACE_ME",

  // Base URL of the deployed "tailorApplication" Cloud Function, used by the
  // Settings -> "Tailor" button for AI CV/statement tailoring. Leave this as
  // an empty string until you've deployed the function (see "Set up AI
  // tailoring" in DEPLOY.md) — the Tailor button will show a helpful message
  // instead of failing silently until this is filled in. Once deployed, the
  // Firebase CLI prints the exact URL to use, e.g.:
  //   https://us-central1-YOUR-PROJECT-ID.cloudfunctions.net/tailorApplication
  // Set this to everything BEFORE the trailing "/tailorApplication", e.g.:
  //   https://us-central1-YOUR-PROJECT-ID.cloudfunctions.net
  cloudFunctionsBaseUrl: ""
};
