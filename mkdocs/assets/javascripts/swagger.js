(function () {
    const SWAGGER_OPTIONS = {
        defaultModelsExpandDepth: -1,
        docExpansion: "full",
    };
    const CURL_CONTINUATION_INDENT = "  ";

    let swaggerCounter = 0;

    function initSwaggerReferences() {
        document.querySelectorAll(".dstack-swagger-ui:not([data-swagger-mounted])").forEach((root) => {
            initSwagger(root).catch((error) => {
                root.dataset.swaggerMounted = "error";
                console.error("Failed to render Swagger UI", error);
            });
        });
    }

    async function initSwagger(root) {
        if (typeof SwaggerUIBundle !== "function") {
            return;
        }
        const url = root.dataset.openapiUrl;
        if (!url) {
            return;
        }

        root.dataset.swaggerMounted = "true";
        if (!root.id) {
            swaggerCounter += 1;
            root.id = `dstack-swagger-ui-${swaggerCounter}`;
        }

        const spec = await fetch(url).then((response) => {
            if (!response.ok) {
                throw new Error(`Failed to load ${url}: ${response.status}`);
            }
            return response.json();
        });
        const swaggerSpec = root.dataset.openapiTag
            ? filterSpecByTag(spec, root.dataset.openapiTag)
            : spec;
        stripSchemaTitles(swaggerSpec);
        const referenceSpec = cloneJson(swaggerSpec);

        SwaggerUIBundle({
            spec: swaggerSpec,
            dom_id: `#${root.id}`,
            ...SWAGGER_OPTIONS,
        });

        setupSummaryToggleGuard();
        setupOperationAnchors(root);
        setupOperationLayout(root, referenceSpec);
        setupOperationTocScrolling(root);
        setupRequestCurlExamples(root, referenceSpec);
        setupSchemaNameBadges(root, referenceSpec);
        setupModelPropertyLabels(root, referenceSpec);
        setupAuthorizationDialogLabels();
    }

    function cloneJson(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function filterSpecByTag(spec, tagName) {
        const paths = {};

        Object.entries(spec.paths || {}).forEach(([path, pathItem]) => {
            if (!pathItem || typeof pathItem !== "object") {
                return;
            }

            const filteredPathItem = {};
            let hasTaggedOperation = false;

            Object.entries(pathItem).forEach(([key, value]) => {
                if (!isHttpMethod(key)) {
                    filteredPathItem[key] = value;
                    return;
                }
                if (!value || typeof value !== "object") {
                    return;
                }

                const operationTags = Array.isArray(value.tags) && value.tags.length > 0
                    ? value.tags
                    : ["default"];
                if (!operationTags.includes(tagName)) {
                    return;
                }

                filteredPathItem[key] = {
                    ...value,
                    tags: [tagName],
                };
                hasTaggedOperation = true;
            });

            if (hasTaggedOperation) {
                paths[path] = filteredPathItem;
            }
        });

        return {
            ...spec,
            tags: getFilteredTags(spec, tagName),
            paths,
        };
    }

    function getFilteredTags(spec, tagName) {
        const tags = (spec.tags || []).filter((tag) => {
            return tag && typeof tag === "object" && tag.name === tagName;
        });
        return tags.length > 0 ? tags : [{ name: tagName }];
    }

    function isHttpMethod(key) {
        return ["get", "put", "post", "delete", "options", "head", "patch", "trace"].includes(
            key.toLowerCase()
        );
    }

    function setupOperationAnchors(root) {
        let scheduled = false;
        const update = () => {
            scheduled = false;
            updateOperationAnchors(root);
        };
        const scheduleUpdate = () => {
            if (scheduled) {
                return;
            }
            scheduled = true;
            window.requestAnimationFrame(update);
        };

        const observer = new MutationObserver(scheduleUpdate);
        observer.observe(root, {
            childList: true,
            subtree: true,
        });
        window.addEventListener("resize", scheduleUpdate);
        scheduleUpdate();
    }

    function setupOperationLayout(root, spec) {
        let scheduled = false;
        const update = () => {
            scheduled = false;
            updateOperationLayout(root, spec);
        };
        const scheduleUpdate = () => {
            if (scheduled) {
                return;
            }
            scheduled = true;
            window.requestAnimationFrame(update);
        };

        const observer = new MutationObserver(scheduleUpdate);
        observer.observe(root, {
            childList: true,
            subtree: true,
        });
        root.addEventListener("input", scheduleUpdate, true);
        scheduleUpdate();
    }

    function updateOperationAnchors(root) {
        const anchors = getOperationAnchors(root);
        if (anchors.size === 0) {
            return;
        }

        root.querySelectorAll(".opblock").forEach((opblock) => {
            const key = getOperationKeyForOpblock(opblock);
            const anchor = key ? anchors.get(key) : null;
            if (!anchor) {
                return;
            }
            anchor.classList.add("dstack-swagger-operation-title");
            if (anchor.parentElement === opblock) {
                return;
            }
            opblock.insertBefore(anchor, opblock.firstChild);
        });

        scrollToCurrentOperationHash(root);
        window.dispatchEvent(new Event("dstack:toc-update"));
    }

    function updateOperationLayout(root, spec) {
        root.querySelectorAll(".opblock").forEach((opblock) => {
            const operation = getOperationForOpblock(spec, opblock);
            makeSummaryStatic(opblock);
            moveOperationDescription(opblock);
            setupOperationUrlCopy(opblock);
            moveOperationHeaderActions(opblock);
            updateParametersSectionState(opblock);
            setupParameterInputPlaceholders(opblock, operation, spec);
            setupParameterMetaLabels(opblock);
            setupResponseBlocks(opblock, operation, spec);
            setupRequestEditors(opblock, operation, spec);
            setupTryOutCancelReset(opblock);
        });
    }

    function setupRequestEditors(opblock, operation, spec) {
        if (!operation) {
            return;
        }
        renameRequestBodyEditTabs(opblock);
        setupRequestBodyEditSchemaPanels(opblock, operation, spec);
        opblock
            .querySelectorAll(":scope .opblock-section-request-body textarea:not(.curl)")
            .forEach((textarea) => {
                const wrapper = textarea.closest(".body-param") || textarea.parentElement;
                wrapper?.classList.add("dstack-editable-code", "dstack-swagger-request-editor");
            });
    }

    function renameRequestBodyEditTabs(opblock) {
        opblock
            .querySelectorAll(":scope .opblock-section-request-body .tablinks")
            .forEach((button) => {
                if (/^\s*edit value\s*$/i.test(button.textContent || "")) {
                    button.textContent = "Request Body";
                } else if (/^\s*schema\s*$/i.test(button.textContent || "")) {
                    button.textContent = "Request Body Schema";
                }
            });
    }

    function setupRequestBodyEditSchemaPanels(opblock, operation, spec) {
        const schema = getRequestJsonSchema(operation, opblock);
        const modelExample = opblock.querySelector(
            ":scope .opblock-section-request-body .model-example"
        );
        if (!modelExample) {
            return;
        }

        modelExample.classList.remove("dstack-swagger-edit-schema-active");
        const editor = modelExample.querySelector(":scope > .dstack-swagger-edit-request-schema");
        if (editor) {
            editor.hidden = true;
        }
        if (!schema || !isRequestBodyEditing(modelExample)) {
            return;
        }
        const schemaTab = [...modelExample.querySelectorAll(".tablinks")].find((button) => {
            return /request body schema|schema/i.test(button.textContent || "");
        });
        if (!schemaTab || !isSwaggerTabActive(schemaTab)) {
            return;
        }

        renderEditRequestBodySchemaPanel(modelExample, schema, spec);
    }

    function isSwaggerTabActive(button) {
        return (
            button.getAttribute("aria-selected") === "true" ||
            button.closest("li")?.classList.contains("active") ||
            button.classList.contains("active")
        );
    }

    function renderEditRequestBodySchemaPanel(modelExample, schema, spec) {
        const tab = modelExample.querySelector(":scope > .tab");
        let editor = modelExample.querySelector(":scope > .dstack-swagger-edit-request-schema");
        if (!editor) {
            const container = document.createElement("div");
            container.innerHTML = getJsonEditorHtml(
                "dstack-swagger-json-schema dstack-swagger-edit-request-schema"
            );
            editor = container.firstElementChild;
        }

        if (tab && editor.previousElementSibling !== tab) {
            tab.after(editor);
        } else if (!editor.parentElement) {
            modelExample.appendChild(editor);
        }
        editor.hidden = false;
        modelExample.classList.add("dstack-swagger-edit-schema-active");
        renderJsonSchemaPre(editor, schema, spec);
    }

    function setupTryOutCancelReset(opblock) {
        const resetButtons = getTryOutResetButtons(opblock);
        resetButtons.forEach((button) => {
            button.classList.add("dstack-swagger-hidden-reset");
        });
        opblock.querySelectorAll(".btn.execute").forEach((button) => {
            const row = button.closest(".btn-group") || button.closest(".execute-wrapper");
            row?.classList.add("dstack-swagger-execute-row");
            row?.closest(".execute-wrapper")?.classList.add("dstack-swagger-execute-wrapper");
        });
        opblock.querySelectorAll(".execute-wrapper .btn, .btn-group .btn").forEach((button) => {
            if (/^\s*clear\s*$/i.test(button.textContent || "")) {
                button.classList.add("dstack-swagger-clear-btn");
            }
        });

        getTryOutCancelButtons(opblock).forEach((button) => {
            if (button.dataset.dstackSwaggerCancelResets === "true") {
                return;
            }
            button.dataset.dstackSwaggerCancelResets = "true";
            button.addEventListener("click", () => {
                getTryOutResetButtons(opblock)
                    .find((resetButton) => resetButton !== button)
                    ?.click();
            }, true);
        });
    }

    function getTryOutResetButtons(opblock) {
        return [...opblock.querySelectorAll(".try-out__btn.reset, .try-out .btn.reset")]
            .filter((button) => /reset/i.test(button.textContent || ""));
    }

    function getTryOutCancelButtons(opblock) {
        return [...opblock.querySelectorAll(".try-out__btn.cancel, .try-out .btn.cancel")]
            .filter((button) => /cancel/i.test(button.textContent || ""));
    }

    function makeSummaryStatic(opblock) {
        const summary = opblock.querySelector(":scope > .opblock-summary");
        const control = summary?.querySelector(":scope > .opblock-summary-control");
        if (!control) {
            return;
        }
        control.classList.add("dstack-swagger-summary-static");
        control.setAttribute("aria-expanded", "true");
        control.setAttribute("aria-disabled", "true");
        control.removeAttribute("tabindex");
    }

    function moveOperationDescription(opblock) {
        const summary = opblock.querySelector(":scope > .opblock-summary");
        if (!summary) {
            return;
        }

        const bodyDescriptions = [
            ...opblock.querySelectorAll(
                ":scope > .opblock-body > .opblock-description-wrapper, " +
                    ":scope > .no-margin > .opblock-body > .opblock-description-wrapper"
            ),
        ];
        const sourceDescription = bodyDescriptions[0];
        const description = opblock.querySelector(
            ":scope > .dstack-swagger-operation-description"
        );
        if (!sourceDescription) {
            description?.remove();
            return;
        }

        bodyDescriptions.forEach((item) => {
            item.classList.add("dstack-swagger-source-operation-description");
        });
        const descriptionHtml = sourceDescription.innerHTML;
        let visibleDescription = description;
        if (!visibleDescription) {
            visibleDescription = sourceDescription.cloneNode(false);
            visibleDescription.classList.add("dstack-swagger-operation-description");
            visibleDescription.classList.remove("dstack-swagger-source-operation-description");
        }
        if (visibleDescription.dataset.dstackSwaggerDescriptionHtml !== descriptionHtml) {
            visibleDescription.innerHTML = descriptionHtml;
            visibleDescription.dataset.dstackSwaggerDescriptionHtml = descriptionHtml;
        }
        if (visibleDescription.nextElementSibling === summary) {
            return;
        }
        opblock.insertBefore(visibleDescription, summary);
    }

    function setupSummaryToggleGuard() {
        if (document.documentElement.dataset.dstackSwaggerSummaryGuard === "true") {
            return;
        }
        document.documentElement.dataset.dstackSwaggerSummaryGuard = "true";

        const preventSummaryToggle = (event) => {
            const target = event.target instanceof Element ? event.target : event.target.parentElement;
            if (!target?.closest(".dstack-swagger-ui .opblock > .opblock-summary")) {
                return;
            }
            if (isAllowedSummaryInteraction(target)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
        };

        document.addEventListener("click", preventSummaryToggle, true);
        document.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                preventSummaryToggle(event);
            }
        }, true);
    }

    function setupAuthorizationDialogLabels() {
        if (document.documentElement.dataset.dstackSwaggerAuthLabels === "true") {
            return;
        }
        document.documentElement.dataset.dstackSwaggerAuthLabels = "true";

        let scheduled = false;
        const scheduleUpdate = () => {
            if (scheduled) {
                return;
            }
            scheduled = true;
            window.requestAnimationFrame(() => {
                scheduled = false;
                updateAuthorizationDialogLabels();
            });
        };

        const observer = new MutationObserver(scheduleUpdate);
        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
        scheduleUpdate();
    }

    function updateAuthorizationDialogLabels() {
        document
            .querySelectorAll(
                ".dstack-swagger-ui .swagger-ui .auth-container " +
                    ":is(label, span, p, div)"
            )
            .forEach((element) => {
                if (element.childNodes.length !== 1) {
                    return;
                }
                if ((element.textContent || "").trim() === "Value:") {
                    element.textContent = "User token:";
                }
            });
    }

    function isAllowedSummaryInteraction(target) {
        if (!target) {
            return false;
        }
        if (target.closest(".dstack-swagger-url-copy")) {
            return true;
        }
        if (
            target.closest(
                ".dstack-swagger-summary-url .opblock-summary-path, " +
                    ".dstack-swagger-summary-url .opblock-summary-path__deprecated"
            )
        ) {
            return true;
        }
        if (!target.closest(".dstack-swagger-summary-actions")) {
            return false;
        }
        return Boolean(target.closest("a, button, input, select, textarea, [role='button']"));
    }

    function setupOperationUrlCopy(opblock) {
        const wrapper = opblock.querySelector(
            ":scope > .opblock-summary .opblock-summary-path-description-wrapper"
        );
        const path = wrapper?.querySelector(
            ":scope .opblock-summary-path, :scope .opblock-summary-path__deprecated"
        );
        if (!wrapper || !path) {
            return;
        }

        wrapper.classList.add("dstack-swagger-summary-url");
        path.removeAttribute("role");
        path.removeAttribute("tabindex");
        path.removeAttribute("aria-label");
        path.removeAttribute("title");
        if (path.dataset.dstackSwaggerSelectablePath !== "true") {
            path.addEventListener("click", stopSummaryControlPropagation);
            path.addEventListener("mousedown", stopSummaryControlPropagation);
            path.addEventListener("touchstart", stopSummaryControlPropagation);
            path.dataset.dstackSwaggerSelectablePath = "true";
        }

        let copyButton = wrapper.querySelector(":scope > .dstack-swagger-url-copy");
        if (!copyButton || copyButton.tagName.toLowerCase() !== "span") {
            const nextCopyButton = document.createElement("span");
            if (copyButton) {
                copyButton.replaceWith(nextCopyButton);
            }
            copyButton = nextCopyButton;
            copyButton.className = "dstack-swagger-url-copy";
            copyButton.title = "Copy URL";
            copyButton.setAttribute("aria-label", "Copy URL");
            copyButton.setAttribute("role", "button");
            wrapper.appendChild(copyButton);
        }

        if (copyButton.dataset.dstackSwaggerUrlCopy === "true") {
            return;
        }
        copyButton.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            copyOperationUrl(opblock, copyButton);
        });
        copyButton.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            copyOperationUrl(opblock, copyButton);
        });
        copyButton.dataset.dstackSwaggerUrlCopy = "true";
    }

    function copyOperationUrl(opblock, copyButton) {
        copyText(getOperationUrl(opblock)).then(() => showCopiedHint(copyButton));
    }

    function showCopiedHint(copyButton) {
        if (!copyButton) {
            return;
        }
        copyButton.classList.add("dstack-swagger-url-copy-copied");
        window.clearTimeout(Number(copyButton.dataset.dstackSwaggerCopiedTimeout || 0));
        const timeout = window.setTimeout(() => {
            copyButton.classList.remove("dstack-swagger-url-copy-copied");
            delete copyButton.dataset.dstackSwaggerCopiedTimeout;
        }, 1300);
        copyButton.dataset.dstackSwaggerCopiedTimeout = String(timeout);
    }

    function getOperationUrl(opblock) {
        const path = opblock.querySelector(".opblock-summary-path")?.dataset.path || "";
        const serverUrl = opblock
            .closest(".dstack-swagger-ui")
            ?.querySelector(".scheme-container .servers select")?.value;
        if (!serverUrl || !path) {
            return path;
        }
        return `${serverUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
    }

    function copyText(text) {
        if (!text) {
            return Promise.resolve();
        }
        if (navigator.clipboard?.writeText) {
            return navigator.clipboard.writeText(text).catch(() => copyTextFallback(text));
        }
        return copyTextFallback(text);
    }

    function copyTextFallback(text) {
        const input = document.createElement("textarea");
        input.value = text;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.top = "-1000px";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
        return Promise.resolve();
    }

    function moveOperationHeaderActions(opblock) {
        const summary = opblock.querySelector(":scope > .opblock-summary");
        if (!summary) {
            return;
        }

        const actions = getSummaryActions(summary);
        moveRequestContentType(opblock, actions);
        moveTryOutButton(opblock, actions);
    }

    function moveRequestContentType(opblock, actions) {
        const requestBodyHeader = opblock.querySelector(
            ":scope .opblock-section-request-body > .opblock-section-header"
        );
        const headerContentType = requestBodyHeader?.querySelector(
            ":scope .content-type-wrapper"
        );
        actions
            .querySelectorAll(":scope > .content-type-wrapper:not(.dstack-swagger-content-type-proxy)")
            .forEach((contentType) => contentType.remove());
        if (!headerContentType) {
            actions.querySelector(":scope > .dstack-swagger-content-type-proxy")?.remove();
            requestBodyHeader?.classList.remove("dstack-swagger-request-body-header-hidden");
            return;
        }

        requestBodyHeader?.classList.add("dstack-swagger-request-body-header-hidden");
        headerContentType.classList.add("dstack-swagger-original-control");

        const contentType = getRequestContentTypeProxy(actions, headerContentType);
        if (contentType.parentElement !== actions) {
            actions.appendChild(contentType);
        }
    }

    function moveTryOutButton(opblock, actions) {
        const headerButtons = [
            ...opblock.querySelectorAll(":scope .opblock-section-header .try-out__btn"),
        ];
        const headerButton = headerButtons[0];
        actions
            .querySelectorAll(":scope > .try-out__btn, :scope > .dstack-swagger-try-out-proxy")
            .forEach((button) => button.remove());
        opblock
            .querySelectorAll(".opblock-section-header.dstack-swagger-try-out-source-header")
            .forEach((header) => {
                if (!header.contains(headerButton)) {
                    header.classList.remove("dstack-swagger-try-out-source-header");
                }
            });
        if (!headerButton) {
            opblock.classList.remove("dstack-swagger-has-try-out");
            opblock.style.removeProperty("--dstack-swagger-try-out-top");
            opblock.style.removeProperty("--dstack-swagger-try-out-width");
            actions.querySelector(":scope > .dstack-swagger-try-out-proxy")?.remove();
            return;
        }

        headerButtons.forEach((button) => {
            button.classList.remove("dstack-swagger-original-control");
            button.classList.add("dstack-swagger-summary-try-out");
        });
        headerButton.closest(".opblock-section-header")?.classList.add(
            "dstack-swagger-try-out-source-header"
        );
        opblock.classList.add("dstack-swagger-has-try-out");
        positionTryOutButtons(opblock, headerButtons);
    }

    function getSummaryActions(summary) {
        let actions = summary.querySelector(":scope > .dstack-swagger-summary-actions");
        if (!actions) {
            actions = document.createElement("div");
            actions.className = "dstack-swagger-summary-actions";
            summary.appendChild(actions);
        }
        return actions;
    }

    function positionTryOutButtons(opblock, buttons) {
        const summary = opblock.querySelector(":scope > .opblock-summary");
        if (!summary) {
            return;
        }

        const top =
            summary.offsetTop +
            Math.max(0, (summary.offsetHeight - buttons[0].offsetHeight) / 2);
        let right = 0;
        [...buttons].reverse().forEach((button) => {
            button.style.setProperty("right", `${right}px`);
            button.style.setProperty("top", `${top}px`);
            right += button.offsetWidth + 8;
        });
        const width = Math.max(0, right - 8);
        opblock.style.setProperty("--dstack-swagger-try-out-top", `${top}px`);
        opblock.style.setProperty("--dstack-swagger-try-out-width", `${width}px`);
    }

    function getRequestContentTypeProxy(actions, sourceContentType) {
        let proxy = actions.querySelector(":scope > .dstack-swagger-content-type-proxy");
        if (!proxy) {
            proxy = sourceContentType.cloneNode(true);
            proxy.addEventListener("change", syncRequestContentTypeProxy);
            proxy.addEventListener("input", syncRequestContentTypeProxy);
            proxy.addEventListener("click", stopSummaryControlPropagation);
            proxy.addEventListener("keydown", stopSummaryControlPropagation);
        } else if (proxy.dataset.dstackSwaggerSourceHtml !== sourceContentType.innerHTML) {
            proxy.innerHTML = sourceContentType.innerHTML;
        }
        proxy.className = sourceContentType.className;
        proxy.classList.remove("dstack-swagger-original-control");
        proxy.classList.add(
            "dstack-swagger-summary-content-type",
            "dstack-swagger-content-type-proxy"
        );
        proxy.dataset.dstackSwaggerSourceHtml = sourceContentType.innerHTML;

        const sourceSelect = sourceContentType.querySelector("select");
        const proxySelect = proxy.querySelector("select");
        if (sourceSelect && proxySelect) {
            proxySelect.value = sourceSelect.value;
            proxySelect.disabled = sourceSelect.disabled;
        }
        return proxy;
    }

    function syncRequestContentTypeProxy(event) {
        const proxySelect = event.target.closest("select");
        const opblock = proxySelect?.closest(".opblock");
        const sourceSelect = opblock?.querySelector(
            ":scope .opblock-section-request-body > .opblock-section-header " +
                ".content-type-wrapper:not(.dstack-swagger-content-type-proxy) select"
        );
        if (!proxySelect || !sourceSelect || sourceSelect.value === proxySelect.value) {
            return;
        }
        sourceSelect.value = proxySelect.value;
        sourceSelect.dispatchEvent(new Event("input", { bubbles: true }));
        sourceSelect.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function stopSummaryControlPropagation(event) {
        event.stopPropagation();
    }

    function updateParametersSectionState(opblock) {
        opblock.querySelectorAll(".opblock-section-header").forEach((header) => {
            const title = (header.querySelector("h4")?.textContent || "").trim();
            const container = header.nextElementSibling;
            if (title !== "Parameters" || !container?.classList.contains("parameters-container")) {
                return;
            }

            const isEmpty = container.querySelectorAll(".parameters tbody tr").length === 0;
            header.classList.toggle("dstack-swagger-empty-parameters", isEmpty);
            container.classList.toggle("dstack-swagger-empty-parameters", isEmpty);
        });
    }

    function setupParameterInputPlaceholders(opblock, operation, spec) {
        const parameters = operation ? getOperationParameters(opblock, operation, spec) : [];
        opblock.querySelectorAll(":scope .parameters tbody tr").forEach((row) => {
            const placeholder = getParameterInputPlaceholder(row, parameters);
            row.querySelectorAll(
                "input:not([type='checkbox']):not([type='radio']):not([type='file']), textarea"
            ).forEach((control) => {
                setupParameterInputDirtyTracking(control);
                clearAutoFilledParameterDefault(control, placeholder);
                if (control.dataset.dstackSwaggerParameterPlaceholder === placeholder) {
                    return;
                }
                control.setAttribute("placeholder", placeholder);
                control.dataset.dstackSwaggerParameterPlaceholder = placeholder;
            });
        });
    }

    function getParameterInputPlaceholder(row, parameters) {
        const defaultValue = getParameterDefaultValue(row, parameters);
        if (defaultValue !== null) {
            return `defaults to ${defaultValue}`;
        }
        return row.querySelector(".parameter__name.required") ? "required" : "optional";
    }

    function getParameterDefaultValue(row, parameters) {
        const parameter = getParameterForRow(row, parameters);
        if (parameter?.schema?.default !== undefined) {
            return formatParameterDefaultValue(parameter.schema.default);
        }
        const text = (row.querySelector(".parameter__default")?.textContent || "")
            .replace(/\s+/g, " ")
            .trim();
        const defaultValue = text.replace(/^Default value\s*:\s*/i, "").trim();
        return defaultValue ? defaultValue : null;
    }

    function getParameterForRow(row, parameters) {
        const name = getParameterRowName(row);
        const location = getParameterRowLocation(row);
        if (!name) {
            return null;
        }
        return parameters.find((parameter) => {
            return parameter.name === name && (!location || parameter.in === location);
        }) || null;
    }

    function getParameterRowName(row) {
        const element = row.querySelector(".parameter__name");
        if (!element) {
            return "";
        }
        for (const node of element.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent.trim();
                if (text) {
                    return text;
                }
            }
        }
        return (element.textContent || "")
            .replace(/\brequired\b/gi, "")
            .replace(/\*+$/, "")
            .trim();
    }

    function getParameterRowLocation(row) {
        return (row.querySelector(".parameter__in")?.textContent || "")
            .trim()
            .replace(/^\((.*)\)$/, "$1");
    }

    function formatParameterDefaultValue(value) {
        if (typeof value === "string") {
            return value === "" ? '""' : value;
        }
        return JSON.stringify(value);
    }

    function setupParameterInputDirtyTracking(control) {
        if (control.dataset.dstackSwaggerParameterDirtyTracking === "true") {
            return;
        }
        control.dataset.dstackSwaggerParameterDirtyTracking = "true";
        control.addEventListener("input", () => {
            control.dataset.dstackSwaggerParameterDirty = "true";
        });
    }

    function clearAutoFilledParameterDefault(control, placeholder) {
        const defaultValue = placeholder.replace(/^defaults to\s+/i, "").trim();
        if (
            defaultValue === placeholder ||
            control.dataset.dstackSwaggerParameterDirty === "true" ||
            String(control.value || "").trim() !== defaultValue
        ) {
            return;
        }
        control.value = "";
    }

    function setupParameterMetaLabels(opblock) {
        opblock.querySelectorAll(":scope .parameter__in").forEach((element) => {
            const text = (element.textContent || "").trim();
            const normalized = text.replace(/^\((.*)\)$/, "$1");
            if (normalized && normalized !== text) {
                element.textContent = normalized;
            }
        });
    }

    function setupResponseBlocks(opblock, operation, spec) {
        const wrapper = opblock.querySelector(":scope .responses-wrapper");
        if (!wrapper) {
            return;
        }
        wrapper.classList.add("dstack-swagger-responses");
        hideNativeResponseCaptions(wrapper);
        wrapper.querySelectorAll(".responses-table tbody tr.response").forEach((row) => {
            const code = getResponseCode(row);
            const response = getResponseForCode(operation, code);
            const schema = getContentSchema(response?.content);
            setupResponseBlock(
                row,
                row.closest(".live-responses-table") !== null,
                response,
                schema,
                spec
            );
        });
    }

    function hideNativeResponseCaptions(wrapper) {
        wrapper.querySelectorAll("h4, h5, .opblock-section-header").forEach((element) => {
            const text = (element.textContent || "").trim().toLowerCase();
            if (text === "server response" || text === "responses") {
                element.classList.add("dstack-swagger-native-response-caption");
            }
        });
    }

    function setupResponseBlock(row, isLiveResponse, response, schema, spec) {
        const descriptionCell = row.querySelector(":scope > .response-col_description");
        if (!descriptionCell) {
            return;
        }

        const code = getResponseCode(row);
        const isSuccess = isSuccessResponseCode(code);
        row.classList.add("dstack-swagger-response-block");
        row.classList.toggle("dstack-swagger-response-success", !isLiveResponse && isSuccess);
        row.classList.toggle("dstack-swagger-response-collapsible", !isLiveResponse && !isSuccess);
        row.classList.toggle("dstack-swagger-live-response", isLiveResponse);

        const description =
            row.dataset.dstackSwaggerResponseDescription || getResponseDescription(descriptionCell);
        row.dataset.dstackSwaggerResponseDescription = description;
        const container = getResponseContainer(descriptionCell, isSuccess, isLiveResponse);
        updateResponseContainerTitle(container, code, description, isSuccess, isLiveResponse);
        const body = getResponseContainerBody(container);

        [...descriptionCell.childNodes].forEach((node) => {
            if (node !== container) {
                body.appendChild(node);
            }
        });
        body.querySelector(":scope > .response-col_description__inner")?.remove();
        setupResponseExampleSection(body, response, schema, spec, isLiveResponse);
    }

    function getResponseForCode(operation, code) {
        if (!operation) {
            return null;
        }
        return operation.responses?.[code] || operation.responses?.default || null;
    }

    function setupResponseExampleSection(body, response, schema, spec, isLiveResponse) {
        if (isLiveResponse) {
            body.querySelector(":scope > .dstack-swagger-response-example")?.remove();
            showResponseSources(body);
            return;
        }

        const exampleText = getResponseExampleText(body, response, schema, spec);
        const hasExample = Boolean(exampleText);
        const hasSchema = Boolean(schema && !isEmptySchema(schema));
        if (!hasExample && !hasSchema) {
            body.querySelector(":scope > .dstack-swagger-response-example")?.remove();
            showResponseSources(body);
            return;
        }

        hideResponseSources(body);
        const wrapper = ensureResponseExampleWrapper(body, hasExample, hasSchema);
        if (hasExample) {
            renderJsonEditorPre(
                wrapper.querySelector(".dstack-swagger-response-json-example"),
                exampleText
            );
        }
        if (hasSchema) {
            renderJsonSchemaPre(wrapper.querySelector(".dstack-swagger-response-json-schema"), schema, spec);
        }
        syncResponseExampleMode(wrapper);
    }

    function hideResponseSources(body) {
        body.querySelectorAll(
            ".response-controls, .model-example, .model-box, .json-schema-2020-12, " +
                ".highlight-code"
        ).forEach((element) => {
            element.classList.add("dstack-swagger-response-source");
        });
    }

    function showResponseSources(body) {
        body.querySelectorAll(".dstack-swagger-response-source")
            .forEach((element) => {
                element.classList.remove("dstack-swagger-response-source");
            });
    }

    function ensureResponseExampleWrapper(body, hasExample, hasSchema) {
        const signature = `${hasExample ? "example" : ""}:${hasSchema ? "schema" : ""}`;
        let wrapper = body.querySelector(":scope > .dstack-swagger-response-example");
        if (wrapper?.dataset.dstackSwaggerResponsePanels === signature) {
            return wrapper;
        }

        if (!wrapper) {
            wrapper = document.createElement("div");
            wrapper.className = "dstack-swagger-response-example";
            body.appendChild(wrapper);
        }
        wrapper.dataset.dstackSwaggerResponsePanels = signature;
        const tabs = hasExample && hasSchema
            ? `
                <ul class="tab dstack-swagger-response-example-tabs" role="tablist">
                    <li class="active">
                        <button class="tablinks dstack-swagger-response-example-tab" type="button" role="tab" aria-selected="true">Response Body Example</button>
                    </li>
                    <li>
                        <button class="tablinks dstack-swagger-response-schema-tab" type="button" role="tab" aria-selected="false">Response Body Schema</button>
                    </li>
                </ul>
            `
            : "";
        wrapper.innerHTML = `
            ${tabs}
            ${hasExample ? `
                <div class="dstack-swagger-response-example-panel" role="tabpanel">
                    ${getJsonEditorHtml("dstack-swagger-response-json-example")}
                </div>
            ` : ""}
            ${hasSchema ? `
                <div class="dstack-swagger-response-schema-panel" role="tabpanel" ${hasExample ? "hidden" : ""}>
                    ${getJsonEditorHtml("dstack-swagger-json-schema dstack-swagger-response-json-schema")}
                </div>
            ` : ""}
        `;

        wrapper
            .querySelector(".dstack-swagger-response-example-tab")
            ?.addEventListener("click", () => setResponseExampleMode(wrapper, "example"));
        wrapper
            .querySelector(".dstack-swagger-response-schema-tab")
            ?.addEventListener("click", () => setResponseExampleMode(wrapper, "schema"));
        return wrapper;
    }

    function setResponseExampleMode(wrapper, mode) {
        wrapper.dataset.dstackSwaggerResponseExampleMode = mode;
        syncResponseExampleMode(wrapper);
    }

    function syncResponseExampleMode(wrapper) {
        const examplePanel = wrapper.querySelector(".dstack-swagger-response-example-panel");
        const schemaPanel = wrapper.querySelector(".dstack-swagger-response-schema-panel");
        const mode = wrapper.dataset.dstackSwaggerResponseExampleMode ||
            (examplePanel ? "example" : "schema");
        const isSchema = mode === "schema" && Boolean(schemaPanel);

        if (examplePanel) {
            examplePanel.hidden = isSchema;
        }
        if (schemaPanel) {
            schemaPanel.hidden = !isSchema;
        }
        wrapper.querySelectorAll(".tab li").forEach((item) => item.classList.remove("active"));
        wrapper.querySelectorAll(".tablinks").forEach((button) => {
            const selected =
                (isSchema && button.classList.contains("dstack-swagger-response-schema-tab")) ||
                (!isSchema && button.classList.contains("dstack-swagger-response-example-tab"));
            button.setAttribute("aria-selected", selected ? "true" : "false");
            button.closest("li")?.classList.toggle("active", selected);
        });

    }

    function getResponseExampleText(body, response, schema, spec) {
        return (
            getResponseExampleTextFromSpec(response) ||
            getResponseExampleTextFromDom(body) ||
            getResponseExampleTextFromSchema(schema, spec)
        );
    }

    function getResponseExampleTextFromSpec(response) {
        const media = getResponseMedia(response);
        if (!media) {
            return "";
        }
        if (media.example !== undefined) {
            return stringifyJsonValue(media.example);
        }

        const firstExample = Object.values(media.examples || {})[0];
        if (firstExample?.value !== undefined) {
            return stringifyJsonValue(firstExample.value);
        }
        return "";
    }

    function getResponseMedia(response) {
        return Object.values(response?.content || {})[0] || null;
    }

    function getResponseExampleTextFromDom(body) {
        const candidates = [
            ...body.querySelectorAll(
                ".model-example .highlight-code pre, .model-example .highlight-code code, " +
                    ".highlight-code pre, .highlight-code code"
            ),
        ];
        for (const candidate of candidates) {
            if (candidate.closest(".dstack-swagger-response-example")) {
                continue;
            }

            const text = normalizeJsonText(candidate.textContent || "");
            if (text && !/^(example value|schema)$/i.test(text)) {
                return text;
            }
        }
        return "";
    }

    function getResponseExampleTextFromSchema(schema, spec) {
        if (!schema || isEmptySchema(schema)) {
            return "";
        }
        const example = buildSchemaExample(schema, spec);
        return example === undefined ? "" : stringifyJsonValue(example);
    }

    function buildSchemaExample(schema, spec, seenRefs = new Set(), depth = 0) {
        if (!schema || typeof schema !== "object") {
            return undefined;
        }
        if (depth > 8) {
            return null;
        }

        if (schema.example !== undefined) {
            return schema.example;
        }
        if (schema.default !== undefined) {
            return schema.default;
        }
        if (Array.isArray(schema.enum) && schema.enum.length > 0) {
            return schema.enum[0];
        }
        if (schema.const !== undefined) {
            return schema.const;
        }

        const refName = getRefName(schema);
        if (refName) {
            if (seenRefs.has(refName)) {
                return {};
            }
            seenRefs.add(refName);
            return buildSchemaExample(resolveSchema(schema, spec), spec, seenRefs, depth + 1);
        }

        if (Array.isArray(schema.allOf) && schema.allOf.length > 0) {
            return mergeSchemaExamples(
                schema.allOf.map((item) => buildSchemaExample(item, spec, seenRefs, depth + 1))
            );
        }

        const union = schema.oneOf || schema.anyOf;
        if (Array.isArray(union) && union.length > 0) {
            return buildSchemaExample(union[0], spec, seenRefs, depth + 1);
        }

        const type = getSchemaExampleType(schema);
        if (type === "array") {
            return [buildSchemaExample(schema.items || {}, spec, seenRefs, depth + 1)];
        }
        if (type === "object") {
            return buildObjectSchemaExample(schema, spec, seenRefs, depth);
        }
        if (type === "integer" || type === "number") {
            return typeof schema.minimum === "number" ? schema.minimum : 0;
        }
        if (type === "boolean") {
            return false;
        }
        if (type === "null") {
            return null;
        }
        return "string";
    }

    function mergeSchemaExamples(examples) {
        const definedExamples = examples.filter((example) => example !== undefined);
        if (definedExamples.every(isPlainObject)) {
            return definedExamples.reduce((merged, example) => ({ ...merged, ...example }), {});
        }
        return definedExamples[definedExamples.length - 1];
    }

    function buildObjectSchemaExample(schema, spec, seenRefs, depth) {
        const properties = getSchemaProperties(schema, spec) || schema.properties;
        if (properties && Object.keys(properties).length > 0) {
            return Object.fromEntries(
                Object.entries(properties).map(([name, propertySchema]) => [
                    name,
                    buildSchemaExample(propertySchema, spec, seenRefs, depth + 1),
                ])
            );
        }
        if (schema.additionalProperties && typeof schema.additionalProperties === "object") {
            return {
                additionalProp1: buildSchemaExample(
                    schema.additionalProperties,
                    spec,
                    seenRefs,
                    depth + 1
                ),
            };
        }
        return {};
    }

    function getSchemaExampleType(schema) {
        if (Array.isArray(schema.type)) {
            return schema.type.find((type) => type !== "null") || "null";
        }
        if (schema.type) {
            return schema.type;
        }
        if (schema.properties || schema.additionalProperties) {
            return "object";
        }
        if (schema.items) {
            return "array";
        }
        return "string";
    }

    function isPlainObject(value) {
        return Boolean(value) && typeof value === "object" && !Array.isArray(value);
    }

    function getResponseCode(row) {
        return (
            row.dataset.code ||
            row.querySelector(":scope > .response-col_status")?.textContent ||
            ""
        ).trim();
    }

    function isSuccessResponseCode(code) {
        return /^2\d\d$/.test(code);
    }

    function getResponseContainer(descriptionCell, isSuccess, isLiveResponse) {
        const tagName = isLiveResponse ? "blockquote" : "details";
        let container = descriptionCell.querySelector(
            ":scope > .dstack-swagger-response-container"
        );
        if (!container) {
            container = descriptionCell.querySelector(
                ":scope > .dstack-swagger-response-admonition"
            );
        }
        if (container?.tagName.toLowerCase() === tagName) {
            updateResponseContainerClass(container, isSuccess, isLiveResponse);
            return container;
        }

        const nextContainer = document.createElement(tagName);
        updateResponseContainerClass(nextContainer, isSuccess, isLiveResponse);
        if (container) {
            while (container.firstChild) {
                nextContainer.appendChild(container.firstChild);
            }
            container.replaceWith(nextContainer);
        } else {
            descriptionCell.prepend(nextContainer);
        }
        return nextContainer;
    }

    function updateResponseContainerClass(container, isSuccess, isLiveResponse) {
        container.className = isLiveResponse
            ? "dstack-swagger-response-container dstack-swagger-response-section dstack-swagger-live-response"
            : "dstack-swagger-response-container info dstack-swagger-response-admonition dstack-swagger-response-section";
    }

    function updateResponseContainerTitle(container, code, description, isSuccess, isLiveResponse) {
        const tagName = isLiveResponse ? "h4" : "summary";
        let title = container.querySelector(":scope > .dstack-swagger-response-title");
        if (title?.tagName.toLowerCase() !== tagName) {
            const nextTitle = document.createElement(tagName);
            if (title) {
                title.replaceWith(nextTitle);
            } else {
                container.prepend(nextTitle);
            }
            title = nextTitle;
        }
        title.className = "dstack-swagger-response-title";
        title.textContent = `${code || "default"} ${description || "Response"}`;
    }

    function getResponseContainerBody(container) {
        let body = container.querySelector(":scope > .dstack-swagger-response-body");
        if (!body) {
            body = document.createElement("div");
            body.className = "dstack-swagger-response-body";
            container.appendChild(body);
        }
        const title = container.querySelector(":scope > .dstack-swagger-response-title");
        if (title && title.nextElementSibling !== body) {
            title.after(body);
        }
        return body;
    }

    function getResponseDescription(descriptionCell) {
        return (
            descriptionCell.querySelector(
                ".response-col_description__inner .renderedMarkdown, " +
                    ".response-col_description__inner"
            )?.textContent ||
            ""
        ).trim();
    }

    function setupRequestCurlExamples(root, spec) {
        let scheduled = false;
        const update = () => {
            scheduled = false;
            updateRequestCurlExamples(root, spec);
        };
        const scheduleUpdate = () => {
            if (scheduled) {
                return;
            }
            scheduled = true;
            window.requestAnimationFrame(update);
        };

        const observer = new MutationObserver(scheduleUpdate);
        observer.observe(root, {
            childList: true,
            subtree: true,
        });
        scheduleUpdate();
    }

    function updateRequestCurlExamples(root, spec) {
        root.querySelectorAll(".opblock").forEach((opblock) => {
            const operation = getOperationForOpblock(spec, opblock);
            if (!operation) {
                return;
            }
            const modelExample = opblock.querySelector(
                ":scope .opblock-section-request-body .model-example"
            );
            if (!modelExample) {
                teardownEditRequestCurlExample(opblock);
                if (!operation.requestBody) {
                    setupOperationCurlExample(opblock, operation, spec);
                }
                return;
            }
            teardownOperationCurlExample(opblock);
            if (isRequestBodyEditing(modelExample)) {
                setupRequestCurlExample(opblock, modelExample, operation, spec, true);
                return;
            }
            setupRequestCurlExample(opblock, modelExample, operation, spec, false);
        });
    }

    function isRequestBodyEditing(modelExample) {
        return Boolean(
            modelExample.querySelector("textarea, .body-param__text") ||
                [...modelExample.querySelectorAll(".tablinks")].some((button) =>
                    /^\s*(edit value|request body)\s*$/i.test(button.textContent || "")
                )
        );
    }

    function teardownRequestCurlExample(modelExample) {
        const wrapper = getRequestCurlWrapper(modelExample);
        wrapper?.remove();
        modelExample.classList.remove("dstack-swagger-request-model-hidden");
    }

    function setupRequestCurlExample(opblock, modelExample, operation, spec, isEditing) {
        const schema = getRequestJsonSchema(operation, opblock);
        if (!schema) {
            teardownRequestCurlExample(modelExample);
            teardownEditRequestCurlExample(opblock);
            return;
        }

        if (isEditing) {
            teardownRequestCurlExample(modelExample);
            teardownEditRequestCurlExample(opblock);
            return;
        }

        const wrapper = ensureRequestCurlWrapper(modelExample);
        wrapper.classList.remove("dstack-swagger-request-example-editing");
        teardownEditRequestCurlExample(opblock);
        const body = getRequestExampleBody(modelExample, operation, opblock);
        const curl = buildCurlCommand(opblock, operation, spec, body);
        renderRequestCurlTermy(wrapper, curl);
        renderRequestJsonSchema(wrapper, schema, spec);

        if (!wrapper.dataset.dstackSwaggerRequestExampleMode) {
            setRequestExampleMode(modelExample, "curl");
        } else {
            syncRequestExampleMode(modelExample);
        }
    }

    function setupOperationCurlExample(opblock, operation, spec) {
        const wrapper = ensureOperationCurlWrapper(opblock);
        const curl = buildCurlCommand(opblock, operation, spec, "");
        renderRequestCurlTermy(wrapper, curl);
    }

    function ensureOperationCurlWrapper(opblock) {
        let wrapper = opblock.querySelector(":scope > .dstack-swagger-operation-curl-example");
        if (wrapper) {
            return wrapper;
        }

        wrapper = document.createElement("div");
        wrapper.className = "dstack-swagger-operation-curl-example";
        wrapper.innerHTML = `
            <div class="termy dstack-swagger-request-curl-termy">
                <div class="highlight"><pre><code></code></pre></div>
            </div>
        `;
        opblock.querySelector(":scope > .opblock-summary")?.after(wrapper);
        return wrapper;
    }

    function teardownOperationCurlExample(opblock) {
        opblock.querySelector(":scope > .dstack-swagger-operation-curl-example")?.remove();
    }

    function getRequestCurlWrapper(modelExample) {
        const previous = modelExample.previousElementSibling;
        return previous?.classList.contains("dstack-swagger-request-example")
            ? previous
            : null;
    }

    function ensureRequestCurlWrapper(modelExample) {
        let wrapper = getRequestCurlWrapper(modelExample);
        if (wrapper) {
            return wrapper;
        }

        wrapper = document.createElement("div");
        wrapper.className = "dstack-swagger-request-example";
        wrapper.innerHTML = `
            <ul class="tab dstack-swagger-request-example-tabs" role="tablist">
                <li class="active">
                    <button class="tablinks dstack-swagger-request-curl-tab" type="button" role="tab" aria-selected="true">cURL Example</button>
                </li>
                <li>
                    <button class="tablinks dstack-swagger-request-schema-tab" type="button" role="tab" aria-selected="false">Request Body Schema</button>
                </li>
            </ul>
            <div class="dstack-swagger-request-curl-panel" role="tabpanel">
                <div class="termy dstack-swagger-request-curl-termy">
                    <div class="highlight"><pre><code></code></pre></div>
                </div>
            </div>
            <div class="dstack-swagger-request-schema-panel" role="tabpanel" hidden>
                ${getJsonEditorHtml("dstack-swagger-json-schema dstack-swagger-request-json-schema")}
            </div>
        `;
        wrapper
            .querySelector(".dstack-swagger-request-curl-tab")
            .addEventListener("click", () => setRequestExampleMode(modelExample, "curl"));
        wrapper
            .querySelector(".dstack-swagger-request-schema-tab")
            .addEventListener("click", () => setRequestExampleMode(modelExample, "schema"));
        modelExample.before(wrapper);
        return wrapper;
    }

    function renderRequestCurlTermy(wrapper, curl) {
        const termy = wrapper.querySelector(".dstack-swagger-request-curl-termy");
        if (!termy || termy.dataset.dstackSwaggerCurl === curl) {
            return;
        }

        termy.dataset.termynalCopy = "true";
        termy.dataset.termynalInstant = "true";
        termy.dataset.termynalMaxHeight = "calc(var(--dstack-swagger-curl-max-height) - 90px)";
        termy.dstackTermynalCopyText = curl;
        termy.innerHTML = '<div class="highlight"><pre><code></code></pre></div>';
        const highlight = termy.querySelector(".highlight");
        highlight.dataset.termynalSingleInput = "true";
        termy.querySelector("code").textContent = `$ ${curl}`;
        termy.dataset.dstackSwaggerCurl = curl;
        if (typeof setupTermynal === "function") {
            setupTermynal(termy);
        }
    }

    function renderRequestJsonSchema(wrapper, schema, spec) {
        const pre = wrapper.querySelector(".dstack-swagger-request-json-schema");
        renderJsonSchemaPre(pre, schema, spec);
    }

    function getJsonEditorHtml(className) {
        return `
            <div class="highlight dstack-scrollable-code dstack-swagger-json-editor ${className}" data-lang="json">
                <pre class="dstack-scrollable-code-pre"><code class="language-json"></code></pre>
            </div>
        `;
    }

    function renderJsonSchemaPre(pre, schema, spec) {
        const schemaDocument = buildJsonSchemaDocument(schema, spec);
        const schemaText = JSON.stringify(orderJsonSchemaKeys(schemaDocument), null, 2);
        renderJsonEditorPre(pre, schemaText);
    }

    function renderJsonEditorPre(editor, text) {
        const code = editor?.querySelector(":scope > pre > code, :scope > code");
        if (!editor || !code) {
            return;
        }

        const jsonText = normalizeJsonText(text);
        setupJsonEditorCopyButton(editor, jsonText);
        if (code.dataset.dstackSwaggerJson === jsonText) {
            return;
        }

        code.innerHTML = highlightJson(jsonText);
        code.dataset.dstackSwaggerJson = jsonText;
    }

    function setupJsonEditorCopyButton(pre, text) {
        let nav = pre.querySelector(":scope > .md-code__nav");
        if (!nav) {
            nav = document.createElement("nav");
            nav.className = "md-code__nav";
            pre.insertBefore(nav, pre.firstChild);
        }

        let button = nav.querySelector(":scope > .md-code__button[data-md-type='copy']");
        if (!button) {
            button = document.createElement("button");
            button.className = "md-code__button";
            button.type = "button";
            button.title = "Copy to clipboard";
            button.dataset.mdType = "copy";
            nav.appendChild(button);
        }
        button.dataset.clipboardText = text;
    }

    function normalizeJsonText(value) {
        const text = String(value || "").trim();
        if (!text) {
            return "";
        }
        try {
            return JSON.stringify(JSON.parse(text), null, 2);
        } catch {
            return text;
        }
    }

    function stringifyJsonValue(value) {
        if (typeof value === "string") {
            return JSON.stringify(value, null, 2);
        }
        return JSON.stringify(value, null, 2);
    }

    function highlightJson(json) {
        return json.replace(
            /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
            (token) => {
                const escaped = escapeHtml(token);
                if (token.startsWith('"')) {
                    const className = token.endsWith(":") ? "nt" : "s2";
                    return `<span class="${className}">${escaped}</span>`;
                }
                if (/true|false|null/.test(token)) {
                    return `<span class="kc">${escaped}</span>`;
                }
                const className = /[.eE]/.test(token) ? "mf" : "mi";
                return `<span class="${className}">${escaped}</span>`;
            }
        );
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function setRequestExampleMode(modelExample, mode) {
        const wrapper = getRequestCurlWrapper(modelExample);
        if (!wrapper) {
            return;
        }

        wrapper.dataset.dstackSwaggerRequestExampleMode = mode;
        syncRequestExampleMode(modelExample);
    }

    function syncRequestExampleMode(modelExample) {
        const wrapper = getRequestCurlWrapper(modelExample);
        if (!wrapper) {
            return;
        }

        const mode = wrapper.dataset.dstackSwaggerRequestExampleMode || "curl";
        const isSchema = mode === "schema";
        const isEditing = wrapper.classList.contains("dstack-swagger-request-example-editing");
        wrapper.querySelector(".dstack-swagger-request-curl-panel").hidden = isSchema;
        wrapper.querySelector(".dstack-swagger-request-schema-panel").hidden = !isSchema;
        wrapper.querySelector(".dstack-swagger-request-curl-tab").closest("li").hidden = isEditing;
        modelExample.classList.toggle("dstack-swagger-request-model-hidden", !isEditing);

        wrapper.querySelectorAll(".tab li").forEach((item) => item.classList.remove("active"));
        wrapper.querySelectorAll(".tablinks").forEach((button) => {
            const selected =
                (isSchema && button.classList.contains("dstack-swagger-request-schema-tab")) ||
                (!isSchema && button.classList.contains("dstack-swagger-request-curl-tab"));
            button.setAttribute("aria-selected", selected ? "true" : "false");
            button.closest("li")?.classList.toggle("active", selected);
        });
    }

    function teardownEditRequestCurlExample(opblock) {
        opblock.querySelector(":scope .dstack-swagger-edit-curl-example")?.remove();
    }

    function getRequestJsonSchema(operation, opblock) {
        const mediaType = getRequestContentType(opblock, operation);
        return operation?.requestBody?.content?.[mediaType]?.schema ||
            getContentSchema(operation?.requestBody?.content);
    }

    function buildJsonSchemaDocument(schema, spec) {
        const definitions = {};
        const seenDefinitions = new Set();
        const addDefinition = (name) => {
            if (!name || seenDefinitions.has(name)) {
                return Boolean(name);
            }
            const componentSchema = spec.components?.schemas?.[name];
            if (!componentSchema) {
                return false;
            }
            seenDefinitions.add(name);
            definitions[name] = transformOpenApiSchemaToJsonSchema(
                componentSchema,
                addDefinition,
                spec
            );
            return true;
        };

        const rootSchema = resolveSchema(schema, spec) || schema;
        const schemaDocument = {
            $schema: "https://json-schema.org/draft/2020-12/schema",
            ...transformOpenApiSchemaToJsonSchema(rootSchema, addDefinition, spec),
        };
        if (Object.keys(definitions).length > 0) {
            schemaDocument.$defs = orderJsonSchemaDefinitions(definitions);
        }
        return schemaDocument;
    }

    function orderJsonSchemaDefinitions(definitions) {
        return Object.fromEntries(
            Object.entries(definitions).map(([name, definition]) => [
                name,
                orderJsonSchemaKeys(definition),
            ])
        );
    }

    function orderJsonSchemaKeys(value) {
        if (Array.isArray(value)) {
            return value.map(orderJsonSchemaKeys);
        }
        if (!value || typeof value !== "object") {
            return value;
        }

        const keyOrder = [
            "$schema",
            "$id",
            "$ref",
            "type",
            "const",
            "enum",
            "required",
            "properties",
            "items",
            "additionalProperties",
            "oneOf",
            "anyOf",
            "allOf",
            "not",
            "format",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "pattern",
            "minItems",
            "maxItems",
            "uniqueItems",
            "description",
            "default",
            "$defs",
        ];
        const ordered = {};
        keyOrder.forEach((key) => {
            if (Object.prototype.hasOwnProperty.call(value, key)) {
                ordered[key] = orderJsonSchemaKeys(value[key]);
            }
        });
        Object.keys(value).forEach((key) => {
            if (!Object.prototype.hasOwnProperty.call(ordered, key)) {
                ordered[key] = orderJsonSchemaKeys(value[key]);
            }
        });
        return ordered;
    }

    function transformOpenApiSchemaToJsonSchema(schema, addDefinition, spec) {
        if (!schema || typeof schema !== "object") {
            return schema;
        }
        if (Array.isArray(schema)) {
            return schema.map((item) =>
                transformOpenApiSchemaToJsonSchema(item, addDefinition, spec)
            );
        }

        const nullable = schema.nullable === true;
        const transformed = {};
        Object.entries(schema).forEach(([key, value]) => {
            if (key === "nullable" || isOpenApiOnlySchemaKeyword(key)) {
                return;
            }

            if (key === "$ref" && typeof value === "string") {
                Object.assign(transformed, transformSchemaRef(value, addDefinition, spec));
                return;
            }

            if (key === "exclusiveMinimum") {
                transformExclusiveLimit(transformed, "minimum", "exclusiveMinimum", value, schema);
                return;
            }
            if (key === "exclusiveMaximum") {
                transformExclusiveLimit(transformed, "maximum", "exclusiveMaximum", value, schema);
                return;
            }

            transformed[key] = transformOpenApiSchemaToJsonSchema(value, addDefinition, spec);
        });
        if (schema.exclusiveMinimum === true && schema.minimum !== undefined) {
            delete transformed.minimum;
        }
        if (schema.exclusiveMaximum === true && schema.maximum !== undefined) {
            delete transformed.maximum;
        }

        return nullable ? addNullableType(transformed) : transformed;
    }

    function isOpenApiOnlySchemaKeyword(key) {
        return ["discriminator", "example", "externalDocs", "xml"].includes(key);
    }

    function transformSchemaRef(ref, addDefinition, spec) {
        const schemaName = getComponentSchemaRefName(ref);
        if (!schemaName) {
            return { $ref: ref };
        }
        if (addDefinition(schemaName)) {
            return { $ref: `#/$defs/${schemaName}` };
        }

        const componentSchema = spec.components?.schemas?.[schemaName];
        if (!componentSchema) {
            return { $ref: ref };
        }
        return { $ref: ref };
    }

    function getComponentSchemaRefName(ref) {
        const prefix = "#/components/schemas/";
        return ref.startsWith(prefix) ? ref.slice(prefix.length) : null;
    }

    function transformExclusiveLimit(target, limitKey, exclusiveKey, value, source) {
        if (typeof value !== "boolean") {
            target[exclusiveKey] = value;
            return;
        }
        if (value && source[limitKey] !== undefined) {
            target[exclusiveKey] = source[limitKey];
            delete target[limitKey];
        }
    }

    function addNullableType(schema) {
        if (typeof schema.type === "string") {
            return {
                ...schema,
                type: schema.type === "null" ? "null" : [schema.type, "null"],
            };
        }
        if (Array.isArray(schema.type)) {
            return {
                ...schema,
                type: schema.type.includes("null") ? schema.type : [...schema.type, "null"],
            };
        }
        return {
            anyOf: [
                schema,
                {
                    type: "null",
                },
            ],
        };
    }

    function getRequestExampleBody(modelExample, operation, opblock) {
        const cached = modelExample.dataset.dstackSwaggerCurlBody;
        const bodyFromDom = getRequestExampleBodyFromDom(modelExample);
        if (bodyFromDom) {
            modelExample.dataset.dstackSwaggerCurlBody = bodyFromDom;
            return bodyFromDom;
        }
        if (cached) {
            return cached;
        }

        const mediaType = getRequestContentType(opblock, operation);
        const bodyFromSpec = getRequestExampleBodyFromSpec(operation, mediaType);
        if (bodyFromSpec) {
            modelExample.dataset.dstackSwaggerCurlBody = bodyFromSpec;
        }
        return bodyFromSpec;
    }

    function getRequestExampleBodyFromDom(modelExample) {
        const candidates = [
            ...modelExample.querySelectorAll("textarea:not(.curl), .body-param__text"),
            ...modelExample.querySelectorAll(
                "[role='tabpanel'] pre, [role='tabpanel'] code, pre, code"
            ),
        ];
        for (const candidate of candidates) {
            const text = (candidate.value || candidate.textContent || "").trim();
            if (looksLikeRequestBody(text)) {
                return text;
            }
        }
        return "";
    }

    function looksLikeRequestBody(text) {
        if (!text || /^(schema|object)$/i.test(text)) {
            return false;
        }
        if (/^\s*[{[]/.test(text)) {
            return true;
        }
        return text.length > 0 && text.length < 10000;
    }

    function getRequestExampleBodyFromSpec(operation, mediaType) {
        const media = operation.requestBody?.content?.[mediaType];
        if (!media) {
            return "";
        }
        if (media.example !== undefined) {
            return stringifyCurlBody(media.example);
        }

        const firstExample = Object.values(media.examples || {})[0];
        if (firstExample?.value !== undefined) {
            return stringifyCurlBody(firstExample.value);
        }
        return "";
    }

    function stringifyCurlBody(value) {
        return typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function buildCurlCommand(opblock, operation, spec, body) {
        const method = (opblock.querySelector(".opblock-summary-method")?.textContent || "GET")
            .trim()
            .toUpperCase();
        const parameters = getOperationParameters(opblock, operation, spec);
        const url = getCurlUrl(opblock, parameters);
        const mediaType = getRequestContentType(opblock, operation);
        const lines = [`curl -X ${method} '${escapeShellSingleQuoted(url)}'`];

        if (hasSecurity(operation, spec)) {
            lines.push("-H 'Authorization: Bearer {user token}'");
        }
        addCurlParameterHeaders(lines, parameters);
        lines.push("-H 'Accept: application/json'");
        if (mediaType) {
            lines.push(`-H 'Content-Type: ${escapeShellSingleQuoted(mediaType)}'`);
        }
        if (body && method !== "GET" && method !== "HEAD") {
            lines.push(formatCurlBodyArgument(body));
        }
        return lines.join(` \\\n${CURL_CONTINUATION_INDENT}`);
    }

    function formatCurlBodyArgument(body) {
        const value = indentCurlBody(escapeShellSingleQuoted(String(body).trim()));
        return `-d '${value}'`;
    }

    function indentCurlBody(value) {
        return value.replace(/\n/g, `\n${CURL_CONTINUATION_INDENT}`);
    }

    function getCurlUrl(opblock, parameters) {
        const url = getOperationUrl(opblock);
        const query = parameters
            .filter((parameter) => parameter.in === "query" && parameter.required)
            .map((parameter) => {
                return `${encodeURIComponent(parameter.name)}=${getParameterPlaceholder(parameter.name)}`;
            })
            .join("&");
        if (!query) {
            return url;
        }
        return `${url}${url.includes("?") ? "&" : "?"}${query}`;
    }

    function addCurlParameterHeaders(lines, parameters) {
        parameters
            .filter((parameter) => parameter.in === "header" && parameter.required)
            .forEach((parameter) => {
                lines.push(
                    `-H '${escapeShellSingleQuoted(parameter.name)}: ${escapeShellSingleQuoted(
                        getParameterPlaceholder(parameter.name)
                    )}'`
                );
            });

        const cookies = parameters
            .filter((parameter) => parameter.in === "cookie" && parameter.required)
            .map((parameter) => {
                return `${parameter.name}=${getParameterPlaceholder(parameter.name)}`;
            });
        if (cookies.length > 0) {
            lines.push(`-H 'Cookie: ${escapeShellSingleQuoted(cookies.join("; "))}'`);
        }
    }

    function getOperationParameters(opblock, operation, spec) {
        const path = opblock.querySelector(".opblock-summary-path")?.dataset.path;
        const pathItem = path ? spec.paths?.[path] : null;
        const parameters = new Map();
        [...(pathItem?.parameters || []), ...(operation.parameters || [])].forEach((parameter) => {
            const resolvedParameter = resolveParameter(parameter, spec);
            if (!resolvedParameter?.name || !resolvedParameter?.in) {
                return;
            }
            parameters.set(`${resolvedParameter.in}:${resolvedParameter.name}`, resolvedParameter);
        });
        return [...parameters.values()];
    }

    function resolveParameter(parameter, spec) {
        if (typeof parameter?.$ref !== "string") {
            return parameter;
        }
        const name = parameter.$ref.split("/").pop();
        return spec.components?.parameters?.[name] || parameter;
    }

    function getParameterPlaceholder(name) {
        return `{${name}}`;
    }

    function getRequestContentType(opblock, operation) {
        return (
            opblock.querySelector(".dstack-swagger-content-type-proxy select")?.value ||
            opblock.querySelector(".opblock-section-request-body .content-type-wrapper select")?.value ||
            Object.keys(operation?.requestBody?.content || {})[0] ||
            ""
        );
    }

    function hasSecurity(operation, spec) {
        if (Array.isArray(operation.security)) {
            return operation.security.length > 0;
        }
        return Array.isArray(spec.security) && spec.security.length > 0;
    }

    function escapeShellSingleQuoted(value) {
        return String(value).replace(/'/g, "'\\''");
    }

    function getOperationAnchors(root) {
        const pageRoot = root.closest(".md-content__inner, .md-typeset, article") || document;
        const anchors = new Map();
        pageRoot.querySelectorAll(".dstack-swagger-operation-anchor").forEach((anchor) => {
            const key = getOperationKey(anchor.dataset.openapiMethod, anchor.dataset.openapiPath);
            if (key) {
                anchors.set(key, anchor);
            }
        });
        return anchors;
    }

    function getOperationKeyForOpblock(opblock) {
        return getOperationKey(
            opblock.querySelector(".opblock-summary-method")?.textContent,
            opblock.querySelector(".opblock-summary-path")?.dataset.path
        );
    }

    function getOperationKey(method, path) {
        const normalizedMethod = (method || "").trim().toLowerCase();
        const normalizedPath = (path || "").trim();
        return normalizedMethod && normalizedPath ? `${normalizedMethod} ${normalizedPath}` : null;
    }

    function setupOperationTocScrolling(root) {
        if (document.documentElement.dataset.dstackSwaggerTocScrolling === "true") {
            return;
        }
        document.documentElement.dataset.dstackSwaggerTocScrolling = "true";

        document.addEventListener("click", (event) => {
            const target = event.target instanceof Element ? event.target : event.target.parentElement;
            const link = target?.closest("a[href*='#']");
            const anchor = getOperationTitleForLink(link);
            if (!anchor) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            window.history.pushState(null, "", `#${anchor.id}`);
            scrollToOperationTitle(anchor, "smooth");
        }, true);

        scrollToCurrentOperationHash(root);
    }

    function scrollToCurrentOperationHash(root) {
        if (root.dataset.dstackSwaggerHashScrolled === "true" || !window.location.hash) {
            return;
        }
        const anchor = document.getElementById(decodeHashId(window.location.hash.slice(1)));
        if (!anchor?.classList.contains("dstack-swagger-operation-title") || !root.contains(anchor)) {
            return;
        }

        root.dataset.dstackSwaggerHashScrolled = "true";
        window.requestAnimationFrame(() => scrollToOperationTitle(anchor));
    }

    function getOperationTitleForLink(link) {
        if (!link) {
            return null;
        }

        const url = new URL(link.getAttribute("href"), window.location.href);
        if (
            url.origin !== window.location.origin ||
            url.pathname !== window.location.pathname ||
            url.search !== window.location.search ||
            !url.hash
        ) {
            return null;
        }

        const anchor = document.getElementById(decodeHashId(url.hash.slice(1)));
        return anchor?.classList.contains("dstack-swagger-operation-title") ? anchor : null;
    }

    function scrollToOperationTitle(anchor, behavior = "auto") {
        const style = window.getComputedStyle(anchor);
        const scrollMargin = Number.parseFloat(style.scrollMarginTop) || 0;
        const top = anchor.getBoundingClientRect().top + window.scrollY - scrollMargin;
        window.scrollTo({ top, behavior });
    }

    function decodeHashId(hashId) {
        try {
            return decodeURIComponent(hashId);
        } catch {
            return hashId;
        }
    }

    function stripSchemaTitles(spec) {
        const seen = new WeakSet();
        const strip = (schema) => {
            if (!schema || typeof schema !== "object" || seen.has(schema)) {
                return;
            }
            seen.add(schema);

            delete schema.title;

            Object.values(schema.properties || {}).forEach(strip);
            ["items", "additionalProperties", "not"].forEach((key) => {
                if (schema[key] && typeof schema[key] === "object") {
                    strip(schema[key]);
                }
            });
            ["allOf", "anyOf", "oneOf"].forEach((key) => {
                if (Array.isArray(schema[key])) {
                    schema[key].forEach(strip);
                }
            });
        };

        Object.values(spec.components?.schemas || {}).forEach(strip);
        Object.values(spec.paths || {}).forEach((pathItem) => {
            Object.values(pathItem || {}).forEach((operation) => {
                (operation.parameters || []).forEach((parameter) => strip(parameter.schema));
                stripContentSchemas(operation.requestBody?.content, strip);
                Object.values(operation.responses || {}).forEach((response) => {
                    stripContentSchemas(response.content, strip);
                });
            });
        });
    }

    function stripContentSchemas(content, strip) {
        Object.values(content || {}).forEach((mediaType) => {
            strip(mediaType?.schema);
        });
    }

    function setupSchemaNameBadges(root, spec) {
        let scheduled = false;
        const update = () => {
            scheduled = false;
            updateSchemaNameBadges(root, spec);
        };
        const scheduleUpdate = () => {
            if (scheduled) {
                return;
            }
            scheduled = true;
            window.requestAnimationFrame(update);
        };

        const observer = new MutationObserver(scheduleUpdate);
        observer.observe(root, {
            childList: true,
            subtree: true,
        });
        scheduleUpdate();
    }

    function setupModelPropertyLabels(root, spec) {
        let scheduled = false;
        const update = () => {
            scheduled = false;
            updateModelPropertyLabels(root, spec);
        };
        const scheduleUpdate = () => {
            if (scheduled) {
                return;
            }
            scheduled = true;
            window.requestAnimationFrame(update);
        };

        const observer = new MutationObserver(scheduleUpdate);
        observer.observe(root, {
            childList: true,
            subtree: true,
        });
        scheduleUpdate();
    }

    function updateSchemaNameBadges(root, spec) {
        root.querySelectorAll(".opblock").forEach((opblock) => {
            const operation = getOperationForOpblock(spec, opblock);
            if (!operation) {
                return;
            }

            const schemas = getOperationSchemas(operation);
            opblock.querySelectorAll(".model-example").forEach((modelExample, index) => {
                const schema = schemas[index];
                if (!schema) {
                    return;
                }
                const rootArticle = modelExample.querySelector(".model-box > .json-schema-2020-12");
                if (rootArticle) {
                    updateSchemaArticle(rootArticle, schema, spec);
                }
            });
        });
    }

    function getOperationForOpblock(spec, opblock) {
        const method = (opblock.querySelector(".opblock-summary-method")?.textContent || "")
            .trim()
            .toLowerCase();
        const path = opblock.querySelector(".opblock-summary-path")?.dataset.path;
        if (!method || !path) {
            return null;
        }
        return spec.paths?.[path]?.[method] || null;
    }

    function getOperationSchemas(operation) {
        const schemas = [];
        const requestSchema = getContentSchema(operation.requestBody?.content);
        if (requestSchema && !isEmptySchema(requestSchema)) {
            schemas.push(requestSchema);
        }

        Object.values(operation.responses || {}).forEach((response) => {
            const responseSchema = getContentSchema(response.content);
            if (responseSchema && !isEmptySchema(responseSchema)) {
                schemas.push(responseSchema);
            }
        });
        return schemas;
    }

    function getContentSchema(content) {
        for (const mediaType of Object.values(content || {})) {
            if (mediaType?.schema) {
                return mediaType.schema;
            }
        }
        return null;
    }

    function isEmptySchema(schema) {
        return Object.keys(schema || {}).length === 0;
    }

    function updateModelPropertyLabels(root, spec) {
        root.querySelectorAll(".opblock").forEach((opblock) => {
            const operation = getOperationForOpblock(spec, opblock);
            if (!operation) {
                return;
            }

            const schemas = getOperationSchemas(operation);
            opblock.querySelectorAll(".model-example").forEach((modelExample, index) => {
                const schema = schemas[index];
                if (!schema) {
                    return;
                }
                updateModelExample(modelExample, schema, spec);
            });
        });

        root.querySelectorAll(".model-example").forEach((modelExample) => {
            modelExample
                .querySelectorAll('.model-box-control[aria-expanded="true"]')
                .forEach((button) => {
                    const schemaName = getModelSchemaName(button, spec);
                    const schema = schemaName ? spec.components?.schemas?.[schemaName] : null;
                    if (schema) {
                        updateModelWrapperPropertyLabels(button.parentElement, schema, spec);
                    }
                });
            updateModelTitleLabels(modelExample, spec);
            updateBareObjectControlTitles(modelExample);
        });
    }

    function updateModelExample(modelExample, schema, spec) {
        const modelBox = modelExample.querySelector(":scope .model-box");
        if (modelBox) {
            updateModelControlTitle(modelBox.querySelector(":scope > .model-box-control"), schema, spec);
            updateModelWrapperPropertyLabels(modelBox, schema, spec);
        }
        updateModelTitleLabels(modelExample, spec);
        updateBareObjectControlTitles(modelExample);
    }

    function updateModelWrapperPropertyLabels(wrapper, schema, spec) {
        if (!wrapper) {
            return;
        }
        const properties = getSchemaProperties(schema, spec);
        if (!properties) {
            return;
        }

        wrapper
            .querySelectorAll(":scope > .inner-object > table.model > tbody > tr.property-row")
            .forEach((row) => {
                const propertyName = getPropertyRowName(row);
                const propertySchema = properties[propertyName];
                const label = getSimpleSchemaLabel(propertySchema, spec);
                if (label) {
                    setPropertyRowLabel(row, label);
                    return;
                }

                const valueCell = row.cells?.[1];
                updateModelControlTitle(
                    valueCell?.querySelector(".model-box-control"),
                    propertySchema,
                    spec
                );
                updateModelWrapperPropertyLabels(
                    valueCell?.querySelector(".model-box"),
                    propertySchema,
                    spec
                );
            });
    }

    function getModelTitle(button) {
        return (
            button.querySelector(".model-title__text")?.textContent ||
            button.querySelector(".model-title")?.textContent ||
            ""
        ).trim();
    }

    function getModelSchemaName(button, spec) {
        if (!button) {
            return null;
        }
        if (button.dataset.dstackSwaggerSchemaName) {
            return button.dataset.dstackSwaggerSchemaName;
        }
        const title = getModelTitle(button);
        const schemaName = getSchemaNameFromTitle(title, spec);
        if (schemaName) {
            button.dataset.dstackSwaggerSchemaName = schemaName;
        }
        return schemaName;
    }

    function getSchemaNameFromTitle(title, spec) {
        const normalized = (title || "").trim();
        if (!normalized) {
            return null;
        }
        if (spec.components?.schemas?.[normalized]) {
            return normalized;
        }

        return null;
    }

    function getPropertyRowName(row) {
        const name = row.cells?.[0]?.textContent || "";
        return name.trim().replace(/\s*\*$/, "");
    }

    function setPropertyRowLabel(row, label) {
        const valueCell = row.cells?.[1];
        if (!valueCell || valueCell.dataset.dstackSwaggerLabel === label) {
            return;
        }
        valueCell.dataset.dstackSwaggerLabel = label;
        valueCell.replaceChildren();

        const labelNode = document.createElement("span");
        labelNode.className = "dstack-swagger-model-label";
        labelNode.textContent = label;
        valueCell.appendChild(labelNode);
    }

    function updateModelTitleLabels(container, spec) {
        container.querySelectorAll(".model-box-control").forEach((button) => {
            getModelSchemaName(button, spec);
            const title = getModelTitle(button);
            const schema = getSchemaForModelTitle(title, spec);
            if (schema) {
                updateModelControlTitle(button, schema, spec);
            }
        });
    }

    function updateBareObjectControlTitles(container) {
        container.querySelectorAll(".model-box-control").forEach((button) => {
            if (
                button.querySelector(".model-title__text") ||
                button.querySelector(":scope > .dstack-swagger-model-inline-title") ||
                !isBareObjectControl(button)
            ) {
                return;
            }
            insertModelControlTitle(button, "object");
        });
    }

    function isBareObjectControl(button) {
        return Array.from(button.children).some((child) => {
            const text = (child.textContent || "").trim().replace(/\s+/g, "");
            return text === "{...}" || text.startsWith("{...");
        });
    }

    function getSchemaForModelTitle(title, spec) {
        const normalized = (title || "").trim();
        const schemaName = getSchemaNameFromTitle(normalized, spec);
        if (schemaName) {
            return spec.components?.schemas?.[schemaName] || null;
        }

        const arrayMatch = normalized.match(/^array<(.+)>$/i);
        if (arrayMatch) {
            const itemName = arrayMatch[1].trim();
            if (spec.components?.schemas?.[itemName]) {
                return {
                    type: "array",
                    items: {
                        $ref: `#/components/schemas/${itemName}`,
                    },
                };
            }
        }

        return null;
    }

    function updateModelControlTitle(button, schema, spec) {
        const title = button?.querySelector(".model-title__text");
        const label = getModelTitleLabel(schema, spec);
        if (!button || !label) {
            return;
        }
        if (!title) {
            insertModelControlTitle(button, label);
            return;
        }
        if (title.dataset.dstackSwaggerTitle === label) {
            return;
        }
        title.dataset.dstackSwaggerTitle = label;
        title.textContent = label;
    }

    function insertModelControlTitle(button, label) {
        if (button.dataset.dstackSwaggerTitle === label) {
            return;
        }

        const existing = button.querySelector(":scope > .dstack-swagger-model-inline-title");
        if (existing) {
            existing.textContent = label;
            button.dataset.dstackSwaggerTitle = label;
            return;
        }

        const titleNode = document.createElement("span");
        titleNode.className = "dstack-swagger-model-inline-title";
        titleNode.textContent = label;
        button.insertBefore(titleNode, getModelPlaceholderNode(button));
        button.dataset.dstackSwaggerTitle = label;
    }

    function getModelPlaceholderNode(button) {
        const directChildren = Array.from(button.children);
        return (
            directChildren.find((child) => {
                const text = (child.textContent || "").trim();
                return text === "{...}" || text.startsWith("{") || text === "[...]";
            }) ||
            directChildren.find((child) => child.classList.contains("model-toggle")) ||
            button.firstChild
        );
    }

    function getSimpleSchemaLabel(schema, spec) {
        if (!schema) {
            return null;
        }

        const refSchema = resolveSchema(schema, spec);
        if (refSchema && refSchema !== schema) {
            const label = getSimpleSchemaLabel(refSchema, spec);
            if (label) {
                return label;
            }
        }

        if (Array.isArray(schema.allOf) && schema.allOf.length === 1) {
            return getSimpleSchemaLabel(schema.allOf[0], spec);
        }

        const union = schema.anyOf || schema.oneOf;
        if (Array.isArray(union) && union.length > 0) {
            const labels = union.map((item) => getSimpleSchemaLabel(item, spec));
            if (labels.every(Boolean)) {
                return labels.join(" | ");
            }
            return null;
        }

        if (Array.isArray(schema.enum)) {
            return formatEnumValues(schema.enum);
        }

        if (schema.const !== undefined) {
            return formatEnumValue(schema.const);
        }

        if (schema.type === "array") {
            const itemLabel = getSimpleSchemaLabel(schema.items || {}, spec);
            return itemLabel ? `array<${itemLabel}>` : null;
        }

        if (schema.type === "object") {
            const additionalProperties = schema.additionalProperties;
            if (additionalProperties && typeof additionalProperties === "object") {
                const valueLabel = getSimpleSchemaLabel(additionalProperties, spec);
                return valueLabel ? `object<string, ${valueLabel}>` : null;
            }
            return null;
        }

        if (["string", "integer", "number", "boolean", "null"].includes(schema.type)) {
            return schema.type;
        }

        return null;
    }

    function getModelTitleLabel(schema, spec) {
        if (!schema) {
            return null;
        }

        const refSchema = resolveSchema(schema, spec);
        if (refSchema && refSchema !== schema) {
            return getModelTitleLabel(refSchema, spec);
        }

        if (Array.isArray(schema.allOf) && schema.allOf.length === 1) {
            return getModelTitleLabel(schema.allOf[0], spec);
        }

        const union = schema.anyOf || schema.oneOf;
        if (Array.isArray(union) && union.length > 0) {
            const labels = uniqueLabels(union.map((item) => getModelTitleLabel(item, spec)));
            return labels.length > 0 ? labels.join(" | ") : "oneOf";
        }

        const simpleLabel = getSimpleSchemaLabel(schema, spec);
        if (simpleLabel) {
            return simpleLabel;
        }

        if (schema.type === "array") {
            const itemLabel = getModelTitleLabel(schema.items || {}, spec);
            return itemLabel ? `array<${itemLabel}>` : "array";
        }

        if (schema.type === "object" || schema.properties) {
            return "object";
        }

        return null;
    }

    function uniqueLabels(labels) {
        const seen = new Set();
        return labels.filter((label) => {
            if (!label || seen.has(label)) {
                return false;
            }
            seen.add(label);
            return true;
        });
    }

    function formatEnumValue(value) {
        if (value === null) {
            return "null";
        }
        if (value === undefined) {
            return "undefined";
        }
        return String(value);
    }

    function formatEnumValues(values) {
        return values.map(formatEnumValue).join(" | ");
    }

    function updateSchemaArticle(article, schema, spec) {
        const badge = article.querySelector(
            ":scope > .json-schema-2020-12-head .json-schema-2020-12__attribute--primary"
        );
        const label = getModelTitleLabel(schema, spec);
        if (badge && label) {
            const current = (badge.textContent || "").trim();
            const schemaName = getRefName(schema);
            if (schemaName && current === schemaName) {
                badge.textContent = label;
            }
        }

        const resolvedSchema = resolveSchema(schema, spec) || schema;
        updateItemArticle(article, resolvedSchema, spec);
        updatePropertyArticles(article, resolvedSchema, spec);
    }

    function updateItemArticle(article, schema, spec) {
        const itemArticle = article.querySelector(
            ":scope > .json-schema-2020-12-body .json-schema-2020-12-keyword--items > article.json-schema-2020-12"
        );
        if (itemArticle && schema?.items) {
            updateSchemaArticle(itemArticle, schema.items, spec);
        }
    }

    function getSchemaProperties(schema, spec) {
        const resolvedSchema = resolveSchema(schema, spec) || schema;
        if (resolvedSchema?.properties) {
            return resolvedSchema.properties;
        }

        if (Array.isArray(resolvedSchema?.allOf)) {
            return resolvedSchema.allOf.reduce((properties, item) => {
                return {
                    ...properties,
                    ...(getSchemaProperties(item, spec) || {}),
                };
            }, {});
        }

        return null;
    }

    function updatePropertyArticles(article, schema, spec) {
        const properties = resolveSchema(schema, spec)?.properties || schema?.properties;
        if (!properties) {
            return;
        }

        article
            .querySelectorAll(
                ":scope > .json-schema-2020-12-body .json-schema-2020-12-keyword--properties > ul > li > article.json-schema-2020-12"
            )
            .forEach((propertyArticle) => {
                const propertyName = getDirectTitle(propertyArticle);
                const propertySchema = properties[propertyName];
                if (propertySchema) {
                    updateSchemaArticle(propertyArticle, propertySchema, spec);
                }
            });
    }

    function getDirectTitle(article) {
        return (
            article
                .querySelector(":scope > .json-schema-2020-12-head .json-schema-2020-12__title")
                ?.textContent || ""
        ).trim();
    }

    function resolveSchema(schema, spec) {
        const ref = getRef(schema);
        if (!ref) {
            return schema;
        }
        const name = ref.split("/").pop();
        return spec.components?.schemas?.[name] || schema;
    }

    function getRefName(schema) {
        const ref = getRef(schema);
        return ref ? ref.split("/").pop() : null;
    }

    function getRef(schema) {
        if (typeof schema?.$ref === "string") {
            return schema.$ref;
        }
        if (Array.isArray(schema?.allOf) && schema.allOf.length === 1) {
            return getRef(schema.allOf[0]);
        }
        return null;
    }

    if (document.readyState === "loading") {
        window.addEventListener("DOMContentLoaded", initSwaggerReferences);
    } else {
        initSwaggerReferences();
    }
})();
