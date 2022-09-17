window.$crisp = [];
window.CRISP_WEBSITE_ID = "ce56e3b2-a23e-4d3f-9e80-e08c61a2b3cb";
(function () {
    let d = document;
    let s = d.createElement("script");
    s.src = "https://client.crisp.chat/l.js";
    s.async = 1;
    d.getElementsByTagName("head")[0].appendChild(s);
    $crisp.push(["do", "chat:hide"]);
})();

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