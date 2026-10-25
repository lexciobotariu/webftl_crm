// Six boxes for a two-factor code (templates/account/_code_input.html).
// Typing a digit moves to the next box, Backspace on an empty box goes back,
// pasting or autofilling a whole code fills every box, and a full code submits
// the form. People without the phone switch to one field for a recovery code.
window.otpInput = function (length, allowRecovery) {
    return {
        length: length,
        allowRecovery: allowRecovery,
        digits: Array(length).fill(''),
        recovery: false,
        submitted: false,

        get code() {
            return this.digits.join('');
        },

        boxes() {
            return Array.from(this.$root.querySelectorAll('[data-otp-box]'));
        },

        focusBox(index) {
            const box = this.boxes()[Math.max(0, Math.min(index, this.length - 1))];
            if (box) {
                box.focus();
                box.select();
            }
        },

        fill(start, text) {
            const found = (text || '').replace(/\D/g, '').split('');
            if (!found.length) {
                this.digits[start] = '';
                return;
            }
            found.slice(0, this.length - start).forEach((digit, offset) => {
                this.digits[start + offset] = digit;
            });
            this.focusBox(start + found.length);
            this.maybeSubmit();
        },

        onInput(index, event) {
            this.fill(index, event.target.value);
            event.target.value = this.digits[index];
        },

        onPaste(index, event) {
            event.preventDefault();
            this.fill(index, (event.clipboardData || window.clipboardData).getData('text'));
        },

        onKeydown(index, event) {
            if (event.key === 'Backspace' && !this.digits[index] && index > 0) {
                event.preventDefault();
                this.digits[index - 1] = '';
                this.focusBox(index - 1);
            } else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                this.focusBox(index - 1);
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                this.focusBox(index + 1);
            }
        },

        maybeSubmit() {
            if (this.submitted || this.code.length !== this.length) return;
            this.submitted = true;
            this.$nextTick(() => this.$root.closest('form').requestSubmit());
        },

        useRecovery() {
            this.recovery = true;
            this.$nextTick(() => this.$refs.recovery.focus());
        },
    };
};
