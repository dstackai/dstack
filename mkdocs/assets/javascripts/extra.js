controller = (function () {
    let setupEventListeners = function () {
        document.addEventListener('keydown', function (event) {
            if (event.keyCode === 75 && (event.metaKey || event.ctrlKey)) {
                document.querySelector('.md-search__input').focus()
            }
        });
    };
    return {
        init: function () {
            setupEventListeners();
        }
    };
})();

controller.init();

function setupTermynal(root = document) {
    const progressLiteralStart = "---> 100%";
    const promptLiteralStart = "$ ";
    const customPromptLiteralStart = "# ";
    const termynalActivateClass = "termy";
    let termynals = [];

    function createTermynals() {
        root
            .querySelectorAll(`.${termynalActivateClass} .highlight`)
            .forEach(node => {
                const termynalRoot = node.closest(`.${termynalActivateClass}`);
                const text = node.textContent;
                const singleInput = getTermynalOption(node, termynalRoot, "termynalSingleInput") === "true";
                const copyEnabled = getTermynalOption(node, termynalRoot, "termynalCopy") === "true";
                const instant = getTermynalOption(node, termynalRoot, "termynalInstant") === "true";
                const copyText = node.dstackTermynalCopyText ||
                    termynalRoot?.dstackTermynalCopyText ||
                    getTermynalOption(node, termynalRoot, "termynalCopyText") ||
                    text.trimEnd();
                const maxHeight = getTermynalOption(node, termynalRoot, "termynalMaxHeight");
                const lines = text.split(/(?<!\\)\n/)
                const useLines = singleInput
                    ? [{
                        type: "input",
                        value: escapeTermynalValue(
                            text.startsWith(promptLiteralStart)
                                ? text.replace(promptLiteralStart, "").trimEnd()
                                : text.trimEnd()
                        )
                    }]
                    : [];
                let buffer = [];
                function saveBuffer() {
                    if (buffer.length) {
                        let isBlankSpace = true;
                        buffer.forEach(line => {
                            if (line) {
                                isBlankSpace = false;
                            }
                        });
                        const dataValue = {};
                        if (isBlankSpace) {
                            dataValue["delay"] = 0;
                        }
                        if (buffer[buffer.length - 1] === "") {
                            // A last single <br> won't have effect
                            // so put an additional one
                            buffer.push("");
                        }
                        const bufferValue = buffer.join("<br>");
                        dataValue["value"] = bufferValue;
                        useLines.push(dataValue);
                        buffer = [];
                    }
                }
                if (!singleInput) {
                    for (let line of lines) {
                        if (line === progressLiteralStart) {
                            saveBuffer();
                            useLines.push({
                                type: "progress"
                            });
                        } else if (line.startsWith(promptLiteralStart)) {
                            saveBuffer();
                            const value = line.replace(promptLiteralStart, "").trimEnd();
                            useLines.push({
                                type: "input",
                                value: value
                            });
                        } else if (line.startsWith("// ")) {
                            saveBuffer();
                            const value = "💬 " + line.replace("// ", "").trimEnd();
                            useLines.push({
                                value: value,
                                class: "termynal-comment",
                                delay: 0
                            });
                        } else if (line.startsWith(customPromptLiteralStart)) {
                            saveBuffer();
                            const promptStart = line.indexOf(promptLiteralStart);
                            if (promptStart === -1) {
                                console.error("Custom prompt found but no end delimiter", line)
                            }
                            const prompt = line.slice(0, promptStart).replace(customPromptLiteralStart, "")
                            let value = line.slice(promptStart + promptLiteralStart.length);
                            useLines.push({
                                type: "input",
                                value: value,
                                prompt: prompt
                            });
                        } else {
                            buffer.push(line);
                        }
                    }
                    saveBuffer();
                }
                const div = document.createElement("div");
                if (maxHeight) {
                    div.classList.add("dstack-termy-scrollable");
                    div.style.setProperty("--dstack-termy-max-height", maxHeight);
                }
                if (copyEnabled) {
                    div.classList.add("dstack-termy-has-copy");
                }
                node.replaceWith(div);
                const termynal = new Termynal(div, {
                    lineData: useLines,
                    noInit: true,
                    startDelay: instant ? 0 : 300,
                    lineDelay: instant ? 0 : 500,
                    typeDelay: instant ? 0 : 20
                });
                if (copyEnabled) {
                    setupTermynalCopyButton(termynal, copyText);
                }
                termynals.push(termynal);
            });
    }

    function getTermynalOption(node, termynalRoot, name) {
        return node.dataset[name] || termynalRoot?.dataset[name];
    }

    function setupTermynalCopyButton(termynal, copyText) {
        const init = termynal.init.bind(termynal);
        termynal.init = function () {
            init();
            addTermynalCopyButton(termynal.container, copyText);
        };
    }

    function addTermynalCopyButton(container, copyText) {
        let button = container.querySelector(":scope > .dstack-termy-copy");
        if (!button) {
            button = document.createElement("button");
            button.className = "dstack-termy-copy";
            button.type = "button";
            button.title = "Copy";
            button.setAttribute("aria-label", "Copy");
            button.addEventListener("click", event => {
                event.preventDefault();
                copyTermynalText(button.dstackTermynalCopyText || "").then(() => {
                    showTermynalCopiedHint(button);
                });
            });
            container.appendChild(button);
        }
        button.dstackTermynalCopyText = copyText;
    }

    function copyTermynalText(text) {
        if (navigator.clipboard?.writeText) {
            return navigator.clipboard.writeText(text).catch(() => copyTermynalTextFallback(text));
        }
        return copyTermynalTextFallback(text);
    }

    function copyTermynalTextFallback(text) {
        const input = document.createElement("textarea");
        input.value = text;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
        return Promise.resolve();
    }

    function showTermynalCopiedHint(button) {
        button.classList.add("dstack-termy-copy-copied");
        window.clearTimeout(Number(button.dataset.termynalCopiedTimeout || 0));
        const timeout = window.setTimeout(() => {
            button.classList.remove("dstack-termy-copy-copied");
            delete button.dataset.termynalCopiedTimeout;
        }, 1300);
        button.dataset.termynalCopiedTimeout = String(timeout);
    }

    function escapeTermynalValue(value) {
        return value
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function loadVisibleTermynals() {
        termynals = termynals.filter(termynal => {
            if (termynal.container.getBoundingClientRect().top - innerHeight <= 0) {
                termynal.init();
                return false;
            }
            return true;
        });
        if (root !== document && termynals.length === 0) {
            window.removeEventListener("scroll", loadVisibleTermynals);
        }
    }
    window.addEventListener("scroll", loadVisibleTermynals);
    createTermynals();
    loadVisibleTermynals();
}

function setupCustomCodeTitles() {
    document.querySelectorAll("div[editor-title]").forEach(div => {
        let code = div.getElementsByTagName('code')[0];
        // code.setAttribute("editor-title", div.getAttribute("editor-title"))
        let editorTitle = document.createElement("span")
        editorTitle.className = "editor-title"
        editorTitle.innerHTML = div.getAttribute("editor-title")
        code.appendChild(editorTitle)
    });
}

function setupSensitiveTocActiveState() {
    const toc = document.querySelector(".md-sidebar--secondary [data-md-component='toc']");
    if (!toc) {
        return;
    }

    let scheduled = false;
    let syncing = false;

    function scheduleSync() {
        if (scheduled) {
            return;
        }
        scheduled = true;
        window.requestAnimationFrame(syncActiveTocLink);
    }

    function syncActiveTocLink() {
        scheduled = false;

        const items = getTocItems(toc);
        if (items.length === 0) {
            return;
        }

        const activationTop = getTocActivationTop();
        let activeIndex = -1;
        items.forEach((item, index) => {
            if (item.target.getBoundingClientRect().top <= activationTop) {
                activeIndex = index;
            }
        });

        if (activeIndex === -1 && items[0].target.getBoundingClientRect().top <= window.innerHeight) {
            activeIndex = 0;
        }

        syncing = true;
        items.forEach((item, index) => {
            item.link.classList.toggle("md-nav__link--active", index === activeIndex);
            item.link.classList.toggle("md-nav__link--passed", activeIndex !== -1 && index < activeIndex);
        });
        window.requestAnimationFrame(() => {
            syncing = false;
        });
    }

    const observer = new MutationObserver(() => {
        if (!syncing) {
            scheduleSync();
        }
    });
    observer.observe(toc, {
        attributes: true,
        attributeFilter: ["class"],
        subtree: true,
    });

    toc.addEventListener("click", event => {
        const target = event.target instanceof Element ? event.target : event.target.parentElement;
        const link = target?.closest("a.md-nav__link[href*='#']");
        const heading = getTocTargetForLink(link);
        if (!heading) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        window.history.pushState(null, "", `#${heading.id}`);
        scrollToTocTarget(heading, "smooth");
        scheduleSync();
    }, true);

    window.addEventListener("scroll", scheduleSync, { passive: true });
    window.addEventListener("resize", scheduleSync);
    window.addEventListener("hashchange", scheduleSync);
    window.addEventListener("dstack:toc-update", scheduleSync);
    scheduleSync();
}

function getTocItems(toc) {
    return [...toc.querySelectorAll("a.md-nav__link[href*='#']")]
        .map(link => {
            const target = getTocTargetForLink(link);
            return target && isVisibleTocTarget(target) ? { link, target } : null;
        })
        .filter(Boolean);
}

function getTocTargetForLink(link) {
    if (!link) {
        return null;
    }

    const url = new URL(link.getAttribute("href"), window.location.href);
    if (
        url.origin !== window.location.origin ||
        url.pathname !== window.location.pathname ||
        !url.hash
    ) {
        return null;
    }

    return document.getElementById(decodeHashId(url.hash.slice(1)));
}

function isVisibleTocTarget(target) {
    const style = window.getComputedStyle(target);
    const rect = target.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.height > 0;
}

function getTocActivationTop() {
    const header = document.querySelector(".md-header");
    const headerBottom = header?.getBoundingClientRect().bottom || 0;
    return headerBottom + Math.min(120, window.innerHeight * 0.25);
}

function scrollToTocTarget(target, behavior = "auto") {
    const style = window.getComputedStyle(target);
    const scrollMargin = Number.parseFloat(style.scrollMarginTop) || 0;
    const top = target.getBoundingClientRect().top + window.scrollY - scrollMargin;
    window.scrollTo({ top, behavior });
}

function decodeHashId(hashId) {
    try {
        return decodeURIComponent(hashId);
    } catch {
        return hashId;
    }
}

window.addEventListener("DOMContentLoaded", function() {
    let tabs = document.querySelector(".md-tabs")
    let header = document.querySelector(".md-header")
    let search = document.querySelector(".md-search")
    search.parentNode.insertBefore(tabs, search)
    header.classList.add("ready")
    setupTermynal()
    setupCustomCodeTitles()
    setupSensitiveTocActiveState()
});

(function () {
    document.querySelectorAll('.tx-faq__item').forEach(function (faqItem) {
        faqItem.querySelector('.tx-faq__item-title').addEventListener('click', function () {
            if (faqItem.classList.contains('_open')) {
                faqItem.classList.remove('_open')
            } else {
                faqItem.classList.add('_open')
            }
        });
    })

    document.querySelectorAll('a[href^="http"]').forEach(link => {
        if (!link.href.includes(location.hostname)) {
          link.setAttribute('target', '_blank');
          link.setAttribute('rel', 'noopener noreferrer');
        }
      });
})()
