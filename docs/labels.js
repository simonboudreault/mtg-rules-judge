// Page labels. LABELS is copied from scripts/render.py so the web page and the
// artifact read the same; SITE holds the strings only the hosted viewer needs.

export const LABELS = {
  en: {
    nav: { answer: "Answer", cards: "Cards", rules: "Rules", rulings: "Rulings",
           walkthrough: "Walkthrough", confidence: "Confidence", community: "Reddit" },
    kicker: "Rules question", shortAnswer: "Short answer", cards: "Cards", rules: "Relevant rules",
    rulings: "Official rulings", walkthrough: "How it plays out", confidence: "Confidence",
    community: "Reddit discussions", communityKicker: "Unofficial · community opinions",
    crVersion: "Comprehensive Rules effective", generated: "Researched", allCards: "All cards on Scryfall",
    card: "Card", rule: "Rule", ruling: "Ruling", official: "Official", scryfallNote: "Scryfall note", webRuling: "From the web, not verified",
    openOn: "Open on", why: "Why", assumptions: "Assumptions", notRetrieved: "Not retrieved",
    high: "High", medium: "Medium", low: "Low", agrees: "Matches the official sources:",
    yes: "Yes", partly: "Partly", no: "No", unknown: "Unknown",
    noThreads: "No Reddit thread could be retrieved for this question.",
    searchReddit: "Search r/mtgrules yourself", opinions: "Main opinions",
    pinHint: "Click to pin · Esc to close", comments: "comments",
    missingRef: "referenced but not present in the data",
    footer: "Rules text and card data are quoted verbatim from the sources named above. Community opinions " +
            "are summarised, not verified. Check with a judge for tournament play.",
  },
  fr: {
    nav: { answer: "Réponse", cards: "Cartes", rules: "Règles", rulings: "Rulings",
           walkthrough: "Déroulement", confidence: "Confiance", community: "Reddit" },
    kicker: "Question de règles", shortAnswer: "Réponse courte", cards: "Cartes",
    rules: "Règles pertinentes", rulings: "Rulings officiels", walkthrough: "Déroulement",
    confidence: "Confiance", community: "Discussions Reddit",
    communityKicker: "Non officiel · opinions de la communauté",
    crVersion: "Règles complètes en vigueur le", generated: "Recherche effectuée le",
    allCards: "Toutes les cartes sur Scryfall", card: "Carte", rule: "Règle", ruling: "Ruling",
    official: "Officiel", scryfallNote: "Note Scryfall", webRuling: "Copié du web, non vérifié", openOn: "Ouvrir sur", why: "Pourquoi",
    assumptions: "Hypothèses", notRetrieved: "Non récupéré", high: "Élevée", medium: "Moyenne",
    low: "Faible", agrees: "Concorde avec les sources officielles :", yes: "Oui", partly: "En partie",
    no: "Non", unknown: "Inconnu", noThreads: "Aucun fil Reddit n'a pu être récupéré pour cette question.",
    searchReddit: "Chercher vous-même sur r/mtgrules", opinions: "Principales opinions",
    pinHint: "Toucher pour épingler · Échap pour fermer", comments: "commentaires",
    missingRef: "référencé mais absent des données",
    footer: "Le texte des règles et des cartes est cité mot pour mot depuis les sources nommées ci-dessus. " +
            "Les opinions de la communauté sont résumées, pas vérifiées. Consultez un arbitre en tournoi.",
  },
};

// The default community block build.py adds when Claude didn't search (scripts/build.py TEXT).
export const REDDIT_DEFAULT = {
  en: "Not searched for this answer — the official sources settle it. Community threads, if you want them:",
  fr: "Pas cherché pour cette réponse — les sources officielles tranchent. Les fils de la communauté, si vous voulez :",
};

const REPO = "https://github.com/simonboudreault/mtg-rules-judge";

// Values ending in "Html" are trusted markup written here, never data from a link.
export const SITE = {
  en: {
    loading: "Loading card text…",
    unavailable: "Card text unavailable right now.",
    ruleLoading: "Loading…",
    ruleMissing: "This rule isn't available here. Check the official rules:",
    rulingLoading: "Loading…",
    rulingMissing: "This ruling couldn't be loaded from Scryfall.",
    rulingMaybe: "Matched by date only: the wording may have changed since this answer.",
    textChanged: "Oracle text changed since this answer.",
    rulesUpdated: "The Comprehensive Rules were updated since this answer (now effective {now}). The rule text shown is the current version.",
    scryfallDown: "Scryfall couldn't be reached, so card text and rulings are missing. The answer itself is complete; reload the page to try again.",
    damagedLink: "This link was changed on its way here: a character differs from what the plugin wrote, so a word or a reference below may be wrong. Ask Claude for the link again to be sure.",
    truncatedLink: "This link isn't complete: if Claude is still writing the reply, wait for it to finish, then click the link again.",
    flip: "Flip",
    threadsLoading: "Looking for threads on r/mtgrules…",
    threadsNone: "No thread on r/mtgrules names these cards together.",
    threadsLive: "The latest r/mtgrules threads that name these cards, found by this page in the PullPush archive of Reddit. Nobody read or checked them for this answer.",
    sources: "Card text, images and rulings: Scryfall, live.",
    attribution: "Card data and images provided by Scryfall. Unofficial Fan Content permitted under the Fan Content Policy; not endorsed by Wizards of the Coast or Scryfall. Rules text © Wizards of the Coast.",
    boot: "Loading…",
    landingTitle: "MTG rules answers",
    landingHtml: `<p>This page shows answers from the <a href="${REPO}">MTG Rules Judge</a> plugin for Claude.
      Ask Claude a <i>Magic: The Gathering</i> rules question and it replies with a link that opens here.</p>
      <p>Nothing is stored on this site: the whole answer travels inside the link, after the <code>#</code>,
      which your browser never sends to a server. Rules text comes from the Comprehensive Rules bundled with
      the plugin; card text, images and rulings come from Scryfall, and Reddit threads from the PullPush archive.</p>`,
    badLinkTitle: "This link is damaged or incomplete",
    badLinkHtml: `<p>Part of the link was probably lost when it was copied. Ask Claude for the link again in the
      same chat.</p>`,
    tooNewTitle: "This answer needs a newer viewer",
    tooNewHtml: `<p>The link was made by a newer version of the plugin. Reload this page; if it still shows this
      message, try again in a few minutes.</p>`,
    oldBrowserTitle: "This browser can't open answer links",
    oldBrowserHtml: `<p>Answer links need a browser from 2023 or later (Safari 16.4, Chrome 80, Firefox 113).
      Update your browser, or open the answer page Claude attached in the chat.</p>`,
    fixtureTitle: "Fixture not found",
    fixtureHtml: `<p>No test fixture by that name.</p>`,
  },
  fr: {
    loading: "Chargement du texte de la carte…",
    unavailable: "Texte de la carte indisponible pour le moment.",
    ruleLoading: "Chargement…",
    ruleMissing: "Cette règle n'est pas disponible ici. Consultez les règles officielles :",
    rulingLoading: "Chargement…",
    rulingMissing: "Ce ruling n'a pas pu être chargé depuis Scryfall.",
    rulingMaybe: "Retrouvé par la date seulement : le texte a peut-être changé depuis cette réponse.",
    textChanged: "Le texte Oracle a changé depuis cette réponse.",
    rulesUpdated: "Les règles complètes ont été mises à jour depuis cette réponse (en vigueur le {now}). Le texte affiché est la version actuelle.",
    scryfallDown: "Scryfall est injoignable : le texte des cartes et les rulings manquent. La réponse elle-même est complète ; rechargez la page pour réessayer.",
    damagedLink: "Ce lien a été modifié en chemin : un caractère diffère de ce que le plugin a écrit, donc un mot ou une référence ci-dessous peut être faux. Redemandez le lien à Claude pour en être sûr.",
    truncatedLink: "Ce lien n'est pas complet : si Claude est encore en train d'écrire la réponse, attendez qu'il ait fini, puis cliquez de nouveau sur le lien.",
    flip: "Retourner",
    threadsLoading: "Recherche de fils sur r/mtgrules…",
    threadsNone: "Aucun fil de r/mtgrules ne nomme ces cartes ensemble.",
    threadsLive: "Les derniers fils de r/mtgrules qui nomment ces cartes, trouvés par cette page dans l'archive PullPush de Reddit. Personne ne les a lus ni vérifiés pour cette réponse.",
    sources: "Texte des cartes, images et rulings : Scryfall, en direct.",
    attribution: "Données et images des cartes fournies par Scryfall. Contenu de fan non officiel autorisé par la Fan Content Policy ; non approuvé par Wizards of the Coast ni Scryfall. Texte des règles © Wizards of the Coast.",
    boot: "Chargement…",
    landingTitle: "Réponses de règles MTG",
    landingHtml: `<p>Cette page affiche les réponses du plugin <a href="${REPO}">MTG Rules Judge</a> pour Claude.
      Posez à Claude une question de règles de <i>Magic: The Gathering</i> : il répond avec un lien qui s'ouvre ici.</p>
      <p>Rien n'est stocké sur ce site : toute la réponse voyage dans le lien, après le <code>#</code>, que votre
      navigateur n'envoie jamais à un serveur. Le texte des règles vient des règles complètes incluses dans le plugin ;
      le texte des cartes, les images et les rulings viennent de Scryfall, et les fils Reddit de l'archive PullPush.</p>`,
    badLinkTitle: "Ce lien est abîmé ou incomplet",
    badLinkHtml: `<p>Une partie du lien s'est probablement perdue à la copie. Redemandez le lien à Claude dans la
      même conversation.</p>`,
    tooNewTitle: "Cette réponse demande une version plus récente",
    tooNewHtml: `<p>Le lien a été créé par une version plus récente du plugin. Rechargez la page ; si ce message
      reste, réessayez dans quelques minutes.</p>`,
    oldBrowserTitle: "Ce navigateur ne peut pas ouvrir les liens de réponse",
    oldBrowserHtml: `<p>Il faut un navigateur de 2023 ou plus récent (Safari 16.4, Chrome 80, Firefox 113).
      Mettez-le à jour, ou ouvrez la page de réponse jointe dans la conversation.</p>`,
    fixtureTitle: "Fixture introuvable",
    fixtureHtml: `<p>Aucune fixture de test de ce nom.</p>`,
  },
};
