function initPaymentDetails() {
  const payRadios = document.querySelectorAll('input[name="payment_method"]');
  const details = document.getElementById('payment-details');
  const bancolombia = document.getElementById('bancolombia-group');
  const nequi = document.getElementById('nequi-group');
  const efectivo = document.getElementById('efectivo-group');

  function showField(method) {
    if (!details) return;
    details.style.display = 'block';
    bancolombia.style.display = 'none';
    nequi.style.display = 'none';
    efectivo.style.display = 'none';

    if (method === 'bancolombia') bancolombia.style.display = 'block';
    if (method === 'nequi') nequi.style.display = 'block';
    if (method === 'efectivo') efectivo.style.display = 'block';
  }

  payRadios.forEach((radio) => {
    radio.addEventListener('change', () => showField(radio.value));
  });

  const checked = document.querySelector('input[name="payment_method"]:checked');
  if (checked) showField(checked.value);
}

window.addEventListener('DOMContentLoaded', () => {
  initPaymentDetails();
});