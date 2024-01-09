(function () {
    const pricingFilterForm = document.querySelector('.js-pricing-filter-form');

    if (!pricingFilterForm)
       return;

    pricingFilterForm.addEventListener('submit', function (event) {
       event.preventDefault()
    })

    function onChangeFilter () {
       const formData = new FormData(pricingFilterForm);
       const formDataObject = Object.fromEntries(formData);

       const selectedFilters = Object.keys(formDataObject).reduce(function (accumulator, fieldName) {
           if (!formDataObject[fieldName])
               return accumulator;

           return Object.assign(accumulator, {[fieldName]: formDataObject[fieldName]});
       }, {})

       filterCard(selectedFilters);
    }

    pricingFilterForm.querySelectorAll('select').forEach(function (select) {
       select.addEventListener('change', onChangeFilter)
    })

    function filterCard(filters) {
        const cards = document.querySelectorAll('.js-pricing-card');

        cards.forEach(function (card) {
            const isMatched = Object.keys(filters).every(function (fieldName) {
                return card.dataset[fieldName].includes(filters[fieldName])
            })

            if (!isMatched) {
                card.style.display = 'none';
                return;
            }

            card.style.removeProperty('display');
        })
    }
})()
