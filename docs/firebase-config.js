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
  apiKey: "AIzaSyCu2yRwUhDhx2n1qfptYF8W_Y4OCgpBVhY",
  authDomain: "myphd-570f2.firebaseapp.com",
  projectId: "myphd-570f2",
  storageBucket: "myphd-570f2.firebasestorage.app",
  messagingSenderId: "1093973685995",
  appId: "1:1093973685995:web:b1045efa5e529aee90f0ae",

  // Base URL of the deployed "tailorResume" Cloud Function, used by the
  // Settings → "Tailor" button for AI resume tailoring. Leave this as an
  // empty string until you've deployed the function (see "Set up AI resume
  // tailoring" in DEPLOY.md) — the Tailor button will show a helpful message
  // instead of failing silently until this is filled in. Once deployed, the
  // Firebase CLI prints the exact URL to use, e.g.:
  //   https://us-central1-jobs-we-care-you.cloudfunctions.net/tailorResume
  // Set this to everything BEFORE the trailing "/tailorResume", e.g.:
  //   https://us-central1-jobs-we-care-you.cloudfunctions.net
  cloudFunctionsBaseUrl: ""
};
