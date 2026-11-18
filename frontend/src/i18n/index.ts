import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import kk from "./kk.json";
import ru from "./ru.json";

export const LANGUAGES = ["kk", "ru", "en"] as const;
export type Language = (typeof LANGUAGES)[number];
const STORAGE_KEY = "lang";

export function isLanguage(v: unknown): v is Language {
  return typeof v === "string" && (LANGUAGES as readonly string[]).includes(v);
}

function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(saved)) return saved;
  } catch {
    // storage blocked: fall through to the default
  }
  return "kk"; // Kazakh is the default interface language
}

void i18n.use(initReactI18next).init({
  resources: { kk: { translation: kk }, ru: { translation: ru }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: "kk",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: Language): void {
  void i18n.changeLanguage(lang);
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // ignore
  }
  document.documentElement.lang = lang;
}

document.documentElement.lang = i18n.language;

export default i18n;
