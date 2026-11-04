const translations = {
  en: {
    title: "Daniil Isaev",
    description: "Daniil Isaev — Saint Petersburg State University student, programming and projects.",
    navAbout: "about", navProjects: "projects", navContacts: "contact",
    name: "Daniil Isaev", role: "Student, SPbU · Software Engineering '29",
    intro: "I study programming and modern languages, build my technical skills, and take part in projects where I value teamwork and sharing ideas.",
    status: "status: learning · building · collaborating", photoPlaceholder: "Daniil's photo",
    aboutTitle: "about me", bio1: "I was born in Lipetsk and graduated from Gymnasium No. 69 named after Sergei Yesenin. Since 2025, I have been studying Software Engineering at Saint Petersburg State University.",
    bio2: "I am interested in programming and exploring modern languages and development tools. I value open knowledge sharing, commitment to a shared goal, and building useful things together as a team.",
    studiesLabel: "studies", university: "Saint Petersburg State University", programLabel: "program", program: "Software Engineering · 2025–present",
    hometownLabel: "hometown", hometown: "Lipetsk", basedLabel: "based in", based: "Saint Petersburg",
    interestsTitle: "interests", interest1: "software development", interest2: "modern programming languages", interest3: "engineering challenges", interest4: "team projects",
    skillsTitle: "skills", projectsTitle: "projects", sourceLink: "source code on GitHub →", moreProjects: "[ more projects coming soon ]",
    contactsTitle: "get in touch", vkMail: "VK Mail ↗", copyright: "© 2026 Daniil Isaev", navLabel: "Main navigation", languageLabel: "Language",
    photoAlt: "Daniil Isaev", portraitLabel: "Daniil Isaev's photo"
  },
  ru: {
    title: "Исаев Даниил",
    description: "Исаев Даниил — студент СПбГУ, программирование и проекты.",
    navAbout: "обо мне", navProjects: "проекты", navContacts: "контакты",
    name: "Исаев Даниил", role: "Студент СПбГУ · Программная инженерия, набор 2029",
    intro: "Изучаю программирование и современные языки, развиваю технические навыки и участвую в проектах, где ценю командную работу и обмен идеями.",
    status: "статус: учусь · создаю · сотрудничаю", photoPlaceholder: "фото Даниила",
    aboutTitle: "обо мне", bio1: "Родился в Липецке, окончил гимназию № 69 имени Сергея Есенина. С 2025 года учусь на направлении «Программная инженерия» в Санкт-Петербургском государственном университете.",
    bio2: "Интересуюсь программированием, изучаю современные языки и инструменты разработки. В командной работе ценю открытый обмен знаниями, ответственность за общую цель и возможность вместе создавать полезные вещи.",
    studiesLabel: "учусь", university: "Санкт-Петербургский государственный университет", programLabel: "направление", program: "Программная инженерия · 2025 — н. в.",
    hometownLabel: "родной город", hometown: "Липецк", basedLabel: "сейчас живу", based: "Санкт-Петербург",
    interestsTitle: "интересы", interest1: "разработка ПО", interest2: "современные языки программирования", interest3: "инженерные задачи", interest4: "командные проекты",
    skillsTitle: "навыки", projectsTitle: "проекты", sourceLink: "исходный код на GitHub →", moreProjects: "[ новые проекты будут появляться здесь ]",
    contactsTitle: "на связи", vkMail: "Почта VK ↗", copyright: "© 2026 Исаев Даниил", navLabel: "Основная навигация", languageLabel: "Язык",
    photoAlt: "Исаев Даниил", portraitLabel: "Фотография Даниила Исаева"
  }
};

function setLanguage(language) {
  const copy = translations[language] || translations.en;
  document.documentElement.lang = language;
  document.title = copy.title;
  document.querySelector('meta[name="description"]').content = copy.description;
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    const value = copy[element.dataset.i18n];
    if (value !== undefined) element.textContent = value;
  });
  document.querySelector('.nav').setAttribute('aria-label', copy.navLabel);
  document.querySelector('.language-toggle').setAttribute('aria-label', copy.languageLabel);
  document.querySelector('.portrait').setAttribute('aria-label', copy.portraitLabel);
  document.querySelector('.portrait img').alt = copy.photoAlt;
  document.querySelectorAll('[data-set-lang]').forEach((button) => {
    const selected = button.dataset.setLang === language;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  try { localStorage.setItem('site-language', language); } catch (_) {}
}

document.querySelectorAll('[data-set-lang]').forEach((button) => {
  button.addEventListener('click', () => setLanguage(button.dataset.setLang));
});
let initialLanguage = 'en';
try {
  const savedLanguage = localStorage.getItem('site-language');
  if (savedLanguage === 'en' || savedLanguage === 'ru') initialLanguage = savedLanguage;
} catch (_) {}
setLanguage(initialLanguage);