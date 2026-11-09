// Controles opcionais: os formulários continuam funcionando sem JavaScript.
document.querySelectorAll('[data-password]').forEach((button) => {
    const input = document.getElementById(button.dataset.password);
    if (!input) return;
    const label = button.getAttribute('aria-label');
    button.hidden = false;
    button.addEventListener('click', () => {
        const visible = input.type === 'password';
        input.type = visible ? 'text' : 'password';
        button.textContent = visible ? 'Ocultar' : 'Mostrar';
        button.setAttribute('aria-pressed', String(visible));
        button.setAttribute('aria-label', visible ? label.replace('Mostrar', 'Ocultar') : label);
    });
});
