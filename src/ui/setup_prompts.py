"""
Setup Prompts Module
Provides interactive prompts for first-time setup and credential management.
"""

from rich.prompt import Prompt, Confirm
from typing import Optional, Tuple, List, Dict, Any

from src.ui.console import console, ICONS


def mask_token(token: str, show_length: int = 8) -> str:
    """
    Mask a token for secure display, showing only the last N characters.

    Args:
        token: The token to mask
        show_length: Number of characters to show at the end

    Returns:
        Masked token string
    """
    if not token:
        return "***"
    if len(token) <= show_length:
        return "***"
    return "***" + token[-show_length:]


def mask_token_partial(token: str, show_head: int = 4, show_tail: int = 4) -> str:
    """
    Mask a token showing partial head and tail.

    Args:
        token: The token to mask
        show_head: Number of characters to show at the start
        show_tail: Number of characters to show at the end

    Returns:
        Partially masked token string
    """
    if not token:
        return "****"
    if len(token) <= show_head + show_tail + 2:
        return "****"
    return token[:show_head] + "..." + token[-show_tail:]


class SetupPrompts:
    """Provides interactive prompts for credential setup and management."""

    # Credential field definitions for consistent display
    CREDENTIAL_FIELDS = {
        'page_access_token': {
            'display_name': 'Page Access Token',
            'input_label': 'Page Access Token',
            'validator': lambda v: len(v) >= 50,
            'error_msg': 'Token format seems invalid. Facebook tokens are typically long strings.',
            'required': True,
        },
        'page_id': {
            'display_name': 'Page ID',
            'input_label': 'Page ID',
            'validator': lambda v: v.isdigit() and 10 <= len(v) <= 25,
            'error_msg': 'Page ID should be a numeric value (typically 10-25 digits).',
            'required': True,
        },
        'app_id': {
            'display_name': 'App ID',
            'input_label': 'App ID',
            'validator': lambda v: v.isdigit() or v == '',
            'error_msg': 'App ID should be numeric (or leave blank).',
            'required': False,
        },
        'app_secret': {
            'display_name': 'App Secret',
            'input_label': 'App Secret',
            'validator': lambda v: len(v) >= 16 or v == '',
            'error_msg': 'App Secret format seems invalid (or leave blank).',
            'required': False,
        },
    }

    @staticmethod
    def ask_page_access_token() -> str:
        """
        Prompt user for Facebook Page Access Token.

        Returns:
            The access token string
        """
        console.print()
        console.print(f"[header]{ICONS['envelope']} Facebook Page Access Token Required[/header]")
        console.print()

        console.print("[dim]Enter your Facebook Page Access Token from the Graph API Explorer:[/dim]")
        console.print("[dim]URL: https://developers.facebook.com/tools/explorer/[/dim]")
        console.print()

        while True:
            token = Prompt.ask(
                "[cyan]Page Access Token[/cyan]",
                default=""
            )

            if not token:
                console.print(f"[warning]{ICONS['warning']} Access Token is required![/warning]")
                console.print("[dim]Please obtain a token from the Graph API Explorer.[/dim]")
                continue

            # Basic validation - Facebook tokens are long alphanumeric strings
            if len(token) < 50:
                console.print(f"[warning]{ICONS['warning']} Token seems too short. Please verify and try again.[/warning]")
                continue

            # Mask the token for security in display
            display_token = mask_token_partial(token)
            console.print(f"[green]Token preview: {display_token}[/green]")

            if Confirm.ask("[cyan]Is this token correct?[/cyan]", default=True):
                return token.strip()

            console.print("[dim]Please enter the token again.[/dim]")

    @staticmethod
    def ask_page_id() -> str:
        """
        Prompt user for Facebook Page ID.

        Returns:
            The page ID string
        """
        console.print()
        console.print(f"[header]{ICONS['info']} Facebook Page ID Required[/header]")
        console.print()

        console.print("[dim]Enter your Facebook Page ID (numeric):[/dim]")
        console.print("[dim]You can find this in your Facebook Page settings or URL:[/dim]")
        console.print()

        while True:
            page_id = Prompt.ask(
                "[cyan]Page ID[/cyan]",
                default=""
            )

            if not page_id:
                console.print(f"[warning]{ICONS['warning']} Page ID is required![/warning]")
                continue

            # Basic validation - Page IDs are numeric
            if not page_id.isdigit():
                console.print(f"[warning]{ICONS['warning']} Page ID should be numeric. Please enter a valid ID.[/warning]")
                continue

            # Page IDs are typically 15-20 digits
            if len(page_id) < 10 or len(page_id) > 25:
                console.print(f"[warning]{ICONS['warning']} Page ID length seems unusual. Please verify.[/warning]")
                continue

            return page_id.strip()

    @staticmethod
    def ask_app_id() -> Optional[str]:
        """
        Prompt user for Facebook App ID (optional).

        Returns:
            The App ID string or None if skipped
        """
        console.print()
        console.print(f"[header]{ICONS['info']} Facebook App ID (Optional)[/header]")
        console.print()

        console.print("[dim]Enter your Facebook App ID (or press Enter to skip):[/dim]")
        console.print("[dim]App ID can be found in Facebook Developer Portal:[/dim]")
        console.print()

        app_id = Prompt.ask(
            "[cyan]App ID[/cyan]",
            default=""
        )

        if not app_id:
            return None

        if not app_id.isdigit():
            console.print(f"[warning]{ICONS['warning']} App ID should be numeric.[/warning]")
            return app_id.strip() if app_id.strip() else None

        return app_id.strip()

    @staticmethod
    def ask_app_secret() -> Optional[str]:
        """
        Prompt user for Facebook App Secret (optional).

        Returns:
            The App Secret string or None if skipped
        """
        console.print()
        console.print(f"[header]{ICONS['info']} Facebook App Secret (Optional)[/header]")
        console.print()

        console.print("[dim]Enter your Facebook App Secret (or press Enter to skip):[/dim]")
        console.print("[dim]App Secret can be found in Facebook Developer Portal:[/dim]")
        console.print()

        app_secret = Prompt.ask(
            "[cyan]App Secret[/cyan]",
            default=""
        )

        if not app_secret:
            return None

        return app_secret.strip()

    @staticmethod
    def confirm_setup(page_access_token: str, page_id: str,
                      app_id: str = None, app_secret: str = None,
                      cookies_file: str = 'cookies.txt') -> bool:
        """
        Show a summary and ask for confirmation to save credentials.

        Args:
            page_access_token: The access token to save
            page_id: The page ID to save
            app_id: The App ID (optional)
            app_secret: The App Secret (optional)
            cookies_file: Path to cookies.txt file

        Returns:
            True if user confirms, False otherwise
        """
        masked_token = mask_token(page_access_token)

        console.print()
        console.print(f"[header]{ICONS['key']} Setup Summary[/header]")
        console.print()

        console.print("[dim]The following credentials will be saved locally:[/dim]")
        console.print()
        console.print(f"  [cyan]Page ID:[/cyan] {page_id}")
        console.print(f"  [cyan]Access Token:[/cyan] {masked_token}")
        if app_id:
            console.print(f"  [cyan]App ID:[/cyan] {app_id}")
        if app_secret:
            console.print(f"  [cyan]App Secret:[/cyan] {mask_token(app_secret)}")

        console.print()
        console.print("[dim]These values will be used for all future sessions.[/dim]")
        console.print("[dim]No internet connection required - this is completely offline.[/dim]")
        console.print()

        return Confirm.ask(
            "[cyan]Save these credentials and continue?[/cyan]",
            default=True
        )

    @staticmethod
    def confirm_setup_simple(page_access_token: str, page_id: str, cookies_file: str = 'cookies.txt') -> bool:
        """
        Show a summary and ask for confirmation to save credentials.

        Args:
            page_access_token: The access token to save
            page_id: The page ID to save
            cookies_file: Path to cookies.txt file

        Returns:
            True if user confirms, False otherwise
        """
        masked_token = mask_token(page_access_token)

        console.print()
        console.print(f"[header]{ICONS['key']} Setup Summary[/header]")
        console.print()

        console.print("[dim]The following credentials and settings will be saved locally:[/dim]")
        console.print()
        console.print(f"  [cyan]Page ID:[/cyan] {page_id}")
        console.print(f"  [cyan]Access Token:[/cyan] {masked_token}")
        console.print(f"  [cyan]Cookies File:[/cyan] {cookies_file}")
        console.print()

        console.print("[dim]YouTube downloads will use cookies.txt for authentication.[/dim]")
        console.print("[dim]See COOKIES_GUIDE.md for help extracting cookies from your browser.[/dim]")
        console.print()

        return Confirm.ask(
            "[cyan]Save these settings and continue?[/cyan]",
            default=True
        )

    @staticmethod
    def setup_instructions() -> None:
        """Print instructions for getting Facebook credentials."""
        console.print()
        console.print("[header]Getting Started with Facebook Credentials[/header]")
        console.print()
        console.print("[dim]Follow these steps to get your credentials:[/dim]")
        console.print()
        console.print("  1. Go to: https://developers.facebook.com/tools/explorer/")
        console.print("  2. Click 'Get Token' → 'Get User Access Token'")
        console.print("  3. Check 'pages_manage_posts' permission")
        console.print("  4. Click 'Generate Access Token'")
        console.print("  5. Click 'Get Token' → 'Get Page Access Token'")
        console.print("  6. Select your Facebook Page from the dropdown")
        console.print()
        console.print("[dim]Your Page ID can be found in the URL when viewing your Facebook Page:[/dim]")
        console.print("[dim]Example: facebook.com/YOUR_PAGE_NAME → Page ID in settings[/dim]")
        console.print()

    @staticmethod
    def request_credentials(include_optional: bool = True) -> Tuple[str, str, Optional[str], Optional[str]]:
        """
        Request credentials from user with interactive prompts.

        Args:
            include_optional: Whether to request optional App ID and App Secret

        Returns:
            Tuple of (page_access_token, page_id, app_id, app_secret)
        """
        # Show instructions first
        if not Confirm.ask(
            "[cyan]Need help getting started? Show setup instructions?[/cyan]",
            default=False
        ):
            # Ask for required credentials
            token = SetupPrompts.ask_page_access_token()
            page_id = SetupPrompts.ask_page_id()

            if include_optional:
                app_id = SetupPrompts.ask_app_id()
                app_secret = SetupPrompts.ask_app_secret()
            else:
                app_id = None
                app_secret = None

            return token, page_id, app_id, app_secret

        SetupPrompts.setup_instructions()

        # Ask for required credentials
        token = SetupPrompts.ask_page_access_token()
        page_id = SetupPrompts.ask_page_id()

        if include_optional:
            app_id = SetupPrompts.ask_app_id()
            app_secret = SetupPrompts.ask_app_secret()
        else:
            app_id = None
            app_secret = None

        return token, page_id, app_id, app_secret

    @staticmethod
    def show_credentials_stored(credentials: dict) -> None:
        """
        Display stored credentials with proper masking.

        Args:
            credentials: Dictionary of stored credentials
        """
        console.print()
        console.print(f"[header]{ICONS['key']} Stored Credentials[/header]")
        console.print()

        if credentials.get('page_access_token'):
            masked_token = mask_token(credentials['page_access_token'])
            console.print(f"  [green]{ICONS['check']} Page Access Token:[/green] {masked_token}")
        else:
            console.print(f"  [red]{ICONS['warning']} Page Access Token:[/red] [dim]<not set>[/dim]")

        if credentials.get('page_id'):
            console.print(f"  [green]{ICONS['check']} Page ID:[/green] {credentials['page_id']}")
        else:
            console.print(f"  [red]{ICONS['warning']} Page ID:[/red] [dim]<not set>[/dim]")

        if credentials.get('app_id'):
            console.print(f"  [green]{ICONS['check']} App ID:[/green] {credentials['app_id']}")

        if credentials.get('app_secret'):
            masked_secret = mask_token(credentials['app_secret'])
            console.print(f"  [green]{ICONS['check']} App Secret:[/green] {masked_secret}")

        if credentials.get('configured_at'):
            console.print()
            console.print(f"  [dim]Last configured:[/dim] {credentials['configured_at']}")

        console.print()

    @staticmethod
    def prompt_update_credential(field_name: str, current_value: str = None) -> Optional[str]:
        """
        Prompt user to update a specific credential field.

        Args:
            field_name: Name of the field to update
            current_value: Current value (for reference)

        Returns:
            New value or None if user wants to keep current
        """
        field_info = SetupPrompts.CREDENTIAL_FIELDS.get(field_name, {})
        display_name = field_info.get('display_name', field_name)

        console.print()
        console.print(f"[header]{ICONS['edit']} Update {display_name}[/header]")
        console.print()

        if current_value:
            console.print(f"[dim]Current value:[/dim] {mask_token(current_value) if 'token' in field_name else current_value}")
        else:
            console.print("[dim]Current value:[/dim] [dim]<not set>[/dim]")

        console.print()

        while True:
            new_value = Prompt.ask(
                f"[cyan]New {display_name}[/cyan] (press Enter to keep current)",
                default=""
            )

            if not new_value:
                return current_value  # Keep existing value

            if field_info.get('validator'):
                if field_info['validator'](new_value):
                    return new_value.strip()
                else:
                    console.print(f"[warning]{ICONS['warning']} {field_info.get('error_msg', 'Invalid format')}[/warning]")
            else:
                return new_value.strip()

    @staticmethod
    def prompt_select_credential_to_update() -> Optional[str]:
        """
        Prompt user to select which credential to update.

        Returns:
            Field name to update, or None if user wants to exit
        """
        console.print()
        console.print(f"[header]{ICONS['edit']} Update Credentials[/header]")
        console.print()

        console.print("[cyan]Available credential fields:[/cyan]")
        console.print()

        options = []
        option_num = 1

        for field_name, field_info in SetupPrompts.CREDENTIAL_FIELDS.items():
            if field_info.get('required', False):
                symbol = ICONS.get('required', '●')
            else:
                symbol = ICONS.get('info', '○')
            options.append((field_name, symbol))
            console.print(f"  {option_num}. [{symbol}] {field_info.get('display_name', field_name)} (required)" if field_info.get('required') else f"  {option_num}. [{symbol}] {field_info.get('display_name', field_name)}")
            option_num += 1

        console.print()
        console.print(f"  {option_num}. Cancel")
        console.print()

        choice = Prompt.ask(
            "[cyan]Select field to update[/cyan]",
            choices=[str(i) for i in range(1, option_num + 1)],
            default=str(option_num)  # Default to Cancel
        )

        choice_num = int(choice)
        if choice_num == option_num:
            return None

        return options[choice_num - 1][0]

    @staticmethod
    def confirm_setup_simple(page_access_token: str, page_id: str) -> bool:
        """
        Show a summary and ask for confirmation to save credentials.

        Args:
            page_access_token: The access token to save
            page_id: The page ID to save

        Returns:
            True if user confirms, False otherwise
        """
        masked_token = mask_token(page_access_token)

        console.print()
        console.print(f"[header]{ICONS['key']} Setup Summary[/header]")
        console.print()

        console.print("[dim]The following credentials will be saved locally:[/dim]")
        console.print()
        console.print(f"  [cyan]Page ID:[/cyan] {page_id}")
        console.print(f"  [cyan]Access Token:[/cyan] {masked_token}")
        console.print()

        console.print("[dim]These values will be used for all future sessions.[/dim]")
        console.print("[dim]No internet connection required - this is completely offline.[/dim]")
        console.print()

        return Confirm.ask(
            "[cyan]Save these credentials and continue?[/cyan]",
            default=True
        )

    @staticmethod
    def prompt_to_retry() -> bool:
        """Ask user if they want to retry the setup."""
        return Confirm.ask(
            "[cyan]Would you like to try again?[/cyan]",
            default=True
        )

    @staticmethod
    def ask_for_cookie_file() -> str:
        """
        Prompt user for cookies.txt file path.

        Returns:
            Path to cookies.txt file
        """
        console.print()
        console.print(f"[header]{ICONS['info']} YouTube Cookies File[/header]")
        console.print()

        console.print("[dim]Enter the path to your cookies.txt file:[/dim]")
        console.print("[dim]Default: cookies.txt (must be in project folder)[/dim]")
        console.print()

        cookies_file = Prompt.ask(
            "[cyan]Cookies File Path[/cyan]",
            default="cookies.txt"
        )

        return cookies_file.strip()

    @staticmethod
    def show_setup_success(page_id: str, page_name: str = None) -> None:
        """
        Show success message after credentials are saved.

        Args:
            page_id: The saved page ID
            page_name: Optional page display name
        """
        console.print()
        console.print(f"[success]{ICONS['check']} ✓ Page added successfully![/success]")
        console.print()
        console.print(f"[green]  Page ID: {page_id}[/green]")
        if page_name:
            console.print(f"[green]  Page Name: {page_name}[/green]")
        console.print()
        console.print("[dim]You can now use the application without re-entering credentials.[/dim]")
        console.print("[dim]To update credentials later, run setup again.[/dim]")
        console.print()

    @staticmethod
    def show_pages_list(pages: List[Dict[str, Any]], max_pages: int = 5) -> None:
        """
        Display the list of saved pages (multi-page support).

        Args:
            pages: List of page dictionaries
            max_pages: Maximum number of pages allowed
        """
        console.print()
        console.print(f"[header]{ICONS['key']} Saved Pages ({len(pages)}/{max_pages})[/header]")
        console.print()

        if not pages:
            console.print("[dim]No pages saved yet. Add your first page below.[/dim]")
            return

        for i, page in enumerate(pages):
            page_name = page.get('page_name', '') or f"Page {i + 1}"
            page_id = page.get('page_id', 'N/A')
            token = page.get('page_access_token', '')
            masked_token = mask_token(token) if token else '***'

            console.print(f"  [{i + 1}] {page_name}")
            console.print(f"      {[ICONS['page']] if ICONS.get('page') else '🌐'} Page ID: {page_id}")
            console.print(f"      [cyan]Token:[/cyan] {masked_token}")
            if i < len(pages) - 1:
                console.print()

        console.print()

    @staticmethod
    def prompt_select_page(pages: List[Dict[str, Any]], max_pages: int = 5) -> int:
        """
        Prompt user to select a page from the list.

        Args:
            pages: List of page dictionaries
            max_pages: Maximum number of pages allowed

        Returns:
            -1 to add new page, or page index (0-based)
        """
        console.print()
        console.print(f"[header]{ICONS['calendar']} Select Page[/header]")
        console.print()

        if pages:
            SetupPrompts.show_pages_list(pages, max_pages)

        console.print("  0. Add New Page")
        for i, page in enumerate(pages):
            page_name = page.get('page_name', '') or f"Page {i + 1}"
            console.print(f"  {i + 1}. {page_name}")

        console.print()
        max_choice = len(pages) + 1

        choice = Prompt.ask(
            "[cyan]Select action[/cyan]",
            choices=[str(i) for i in range(max_choice + 1)],
            default="1"
        )

        choice_num = int(choice)
        if choice_num == 0:
            return -1  # Add new page
        return choice_num - 1  # Return 0-based index