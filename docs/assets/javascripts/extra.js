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

function setupTermynal() {
    document.querySelectorAll(".use-termynal").forEach(node => {
        node.style.display = "block";
        new Termynal(node, {
            lineDelay: 500
        });
    });
    const progressLiteralStart = "---> 100%";
    const promptLiteralStart = "$ ";
    const customPromptLiteralStart = "# ";
    const termynalActivateClass = "termy";
    let termynals = [];

    function createTermynals() {
        document
            .querySelectorAll(`.${termynalActivateClass} .highlight`)
            .forEach(node => {
                const text = node.textContent;
                const lines = text.split(/(?<!\\)\n/)
                const useLines = [];
                let buffer = [];
                function saveBuffer() {
                    if (buffer.length) {
                        let isBlankSpace = true;
                        buffer.forEach(line => {
                            if (line) {
                                isBlankSpace = false;
                            }
                        });
                        dataValue = {};
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
                const div = document.createElement("div");
                node.replaceWith(div);
                const termynal = new Termynal(div, {
                    lineData: useLines,
                    noInit: true,
                    lineDelay: 500,
                    typeDelay: 20
                });
                termynals.push(termynal);
            });
    }

    function loadVisibleTermynals() {
        termynals = termynals.filter(termynal => {
            if (termynal.container.getBoundingClientRect().top - innerHeight <= 0) {
                termynal.init();
                return false;
            }
            return true;
        });
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

window.addEventListener("DOMContentLoaded", function() {
    let tabs = document.querySelector(".md-tabs")
    let header = document.querySelector(".md-header")
    let search = document.querySelector(".md-search")
    search.parentNode.insertBefore(tabs, search)
    header.classList.add("ready")
    setupTermynal()
    setupCustomCodeTitles()
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
})()
