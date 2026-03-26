# Analyst by Potomac — WinUI 3 Design Guide

> **Matching Design System for Windows 11 / WinUI 3 (Windows App SDK)**
>
> This guide translates the Next.js web frontend into native WinUI 3 XAML + C# equivalents.

---

## Table of Contents

1. [Design Tokens & Resources](#1-design-tokens--resources)
2. [Typography](#2-typography)
3. [Color System](#3-color-system)
4. [Dark & Light Theme](#4-dark--light-theme)
5. [Theme Styles](#5-theme-styles)
6. [Spacing & Layout](#6-spacing--layout)
7. [Component Library](#7-component-library)
8. [Navigation](#8-navigation)
9. [Login & Register](#9-login--register)
10. [Dashboard](#10-dashboard)
11. [Chat Interface](#11-chat-interface)
12. [AFL Generator](#12-afl-generator)
13. [Knowledge Base](#13-knowledge-base)
14. [Settings](#14-settings)
15. [Animations & Transitions](#15-animations--transitions)
16. [Accessibility](#16-accessibility)
17. [Complete App Structure](#17-complete-app-structure)

---

## 1. Design Tokens & Resources

### Theme Resource Dictionary

```xml
<!-- Themes/PotomacTheme.xaml -->
<ResourceDictionary
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <!-- ═══ BRAND COLORS ═══ -->
    <Color x:Key="PotomacAccentColor">#FEC00F</Color>
    <Color x:Key="PotomacAccentLightColor">#FCD34D</Color>
    <Color x:Key="PotomacBlueColor">#60A5FA</Color>
    <Color x:Key="PotomacPurpleColor">#A78BFA</Color>
    <Color x:Key="PotomacGreenColor">#34D399</Color>
    <Color x:Key="PotomacOrangeColor">#FB923C</Color>
    <Color x:Key="PotomacPinkColor">#F472B6</Color>
    <Color x:Key="PotomacCyanColor">#22D3EE</Color>
    <Color x:Key="PotomacRoseColor">#EC4899</Color>

    <!-- Status -->
    <Color x:Key="PotomacSuccessColor">#22C55E</Color>
    <Color x:Key="PotomacWarningColor">#FCD34D</Color>
    <Color x:Key="PotomacErrorColor">#EF4444</Color>
    <Color x:Key="PotomacInfoColor">#60A5FA</Color>

    <!-- ═══ DARK THEME ═══ -->
    <Color x:Key="DarkBackground">#080809</Color>
    <Color x:Key="DarkCard">#0D0D10</Color>
    <Color x:Key="DarkCardHover">#121216</Color>
    <Color x:Key="DarkRaised">#111115</Color>
    <Color x:Key="DarkText">#EFEFEF</Color>
    <Color x:Key="DarkTextMuted">#606068</Color>
    <Color x:Key="DarkTextDim">#2E2E36</Color>

    <!-- ═══ LIGHT THEME ═══ -->
    <Color x:Key="LightBackground">#F5F5F6</Color>
    <Color x:Key="LightCard">#FFFFFF</Color>
    <Color x:Key="LightCardHover">#F9F9FA</Color>
    <Color x:Key="LightRaised">#FAFAFA</Color>
    <Color x:Key="LightText">#0A0A0B</Color>
    <Color x:Key="LightTextMuted">#808088</Color>
    <Color x:Key="LightTextDim">#D8D8DC</Color>

    <!-- ═══ BRUSHES (Dark) ═══ -->
    <SolidColorBrush x:Key="PotomacBackgroundBrush" Color="{StaticResource DarkBackground}"/>
    <SolidColorBrush x:Key="PotomacCardBrush" Color="{StaticResource DarkCard}"/>
    <SolidColorBrush x:Key="PotomacCardHoverBrush" Color="{StaticResource DarkCardHover}"/>
    <SolidColorBrush x:Key="PotomacRaisedBrush" Color="{StaticResource DarkRaised}"/>
    <SolidColorBrush x:Key="PotomacBorderBrush" Color="#0FFFFFFF"/>
    <SolidColorBrush x:Key="PotomacTextBrush" Color="{StaticResource DarkText}"/>
    <SolidColorBrush x:Key="PotomacTextMutedBrush" Color="{StaticResource DarkTextMuted}"/>
    <SolidColorBrush x:Key="PotomacTextDimBrush" Color="{StaticResource DarkTextDim}"/>
    <SolidColorBrush x:Key="PotomacAccentBrush" Color="{StaticResource PotomacAccentColor}"/>
    <SolidColorBrush x:Key="PotomacAccentDimBrush" Color="#14FEC00F"/>
    <SolidColorBrush x:Key="PotomacAccentBorderBrush" Color="#2EFEC00F"/>
    <SolidColorBrush x:Key="PotomacBlueDimBrush" Color="#1460A5FA"/>
    <SolidColorBrush x:Key="PotomacAIBubbleBrush" Color="#08FFFFFF"/>
    <SolidColorBrush x:Key="PotomacSidebarBrush" Color="{StaticResource DarkCard}"/>

    <!-- ═══ LAYOUT ═══ -->
    <x:Double x:Key="PotomacCornerRadius">20</x:Double>
    <x:Double x:Key="PotomacCornerRadiusSmall">10</x:Double>
    <x:Double x:Key="PotomacCornerRadiusLarge">28</x:Double>
    <x:Double x:Key="PotomacCardPadding">28</x:Double>
    <x:Double x:Key="PotomacPagePadding">52</x:Double>
    <x:Double x:Key="PotomacSidebarWidth">256</x:Double>
    <x:Double x:Key="PotomacSidebarCollapsedWidth">80</x:Double>
    <x:Double x:Key="PotomacMaxContentWidth">1360</x:Double>
    <Thickness x:Key="PotomacCardMargin">0,0,0,16</Thickness>
</ResourceDictionary>
```

### App.xaml Integration

```xml
<!-- App.xaml -->
<Application
    x:Class="AnalystApp.App"
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <Application.Resources>
        <ResourceDictionary>
            <ResourceDictionary.MergedDictionaries>
                <XamlControlsResources xmlns="using:Microsoft.UI.Xaml.Controls"/>
                <ResourceDictionary Source="ms-appx:///Themes/PotomacTheme.xaml"/>
                <ResourceDictionary Source="ms-appx:///Styles/PotomacStyles.xaml"/>
                <ResourceDictionary Source="ms-appx:///Styles/PotomacControls.xaml"/>
            </ResourceDictionary.MergedDictionaries>
        </ResourceDictionary>
    </Application.Resources>
</Application>
```

---

## 2. Typography

### Font Resources

```xml
<!-- Themes/PotomacFonts.xaml -->
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">

    <!-- Syne → Segoe UI Variable Display (closest WinUI native) -->
    <!-- DM Mono → Cascadia Mono (Windows built-in monospace) -->
    <!-- Instrument Sans → Segoe UI Variable Text -->

    <!-- If custom fonts are bundled: -->
    <FontFamily x:Key="SyneFont">ms-appx:///Assets/Fonts/Syne-Variable.ttf#Syne</FontFamily>
    <FontFamily x:Key="DMMonoFont">ms-appx:///Assets/Fonts/DM_Mono/DMMono-Regular.ttf#DM Mono</FontFamily>
    <FontFamily x:Key="InstrumentSansFont">ms-appx:///Assets/Fonts/InstrumentSans/InstrumentSans-Regular.ttf#Instrument Sans</FontFamily>

    <!-- Fallback to system fonts: -->
    <FontFamily x:Key="SyneFallback">Segoe UI Variable Display</FontFamily>
    <FontFamily x:Key="DMMonoFallback">Cascadia Mono</FontFamily>
    <FontFamily x:Key="InstrumentSansFallback">Segoe UI Variable Text</FontFamily>

    <!-- ═══ TEXT STYLES ═══ -->

    <!-- Eyebrow Label: DM Mono 9px, UPPERCASE, 0.18em spacing -->
    <Style x:Key="PotomacEyebrowLabel" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource DMMonoFont}"/>
        <Setter Property="FontSize" Value="9"/>
        <Setter Property="FontWeight" Value="Medium"/>
        <Setter Property="CharacterSpacing" Value="18"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextMutedBrush}"/>
    </Style>

    <!-- Heading 1: Syne 52px, ExtraBold, -3% tracking -->
    <Style x:Key="PotomacH1" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
        <Setter Property="FontSize" Value="52"/>
        <Setter Property="FontWeight" Value="ExtraBold"/>
        <Setter Property="CharacterSpacing" Value="-30"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextBrush}"/>
    </Style>

    <!-- Heading 1 Mobile -->
    <Style x:Key="PotomacH1Mobile" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
        <Setter Property="FontSize" Value="36"/>
        <Setter Property="FontWeight" Value="ExtraBold"/>
        <Setter Property="CharacterSpacing" Value="-30"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextBrush}"/>
    </Style>

    <!-- Heading 2: Syne 34px, Bold -->
    <Style x:Key="PotomacH2" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
        <Setter Property="FontSize" Value="34"/>
        <Setter Property="FontWeight" Value="Bold"/>
        <Setter Property="CharacterSpacing" Value="-25"/>
    </Style>

    <!-- Heading 3: Syne 20px, Bold -->
    <Style x:Key="PotomacH3" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
        <Setter Property="FontSize" Value="20"/>
        <Setter Property="FontWeight" Value="Bold"/>
        <Setter Property="CharacterSpacing" Value="-20"/>
    </Style>

    <!-- Body: Segoe UI Variable 14px -->
    <Style x:Key="PotomacBody" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource InstrumentSansFont}"/>
        <Setter Property="FontSize" Value="14"/>
        <Setter Property="TextWrapping" Value="Wrap"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextBrush}"/>
    </Style>

    <!-- Body Muted -->
    <Style x:Key="PotomacBodyMuted" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource InstrumentSansFont}"/>
        <Setter Property="FontSize" Value="14"/>
        <Setter Property="TextWrapping" Value="Wrap"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextMutedBrush}"/>
    </Style>

    <!-- Nav Label: Syne 13px, Bold, UPPERCASE -->
    <Style x:Key="PotomacNavLabel" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
        <Setter Property="FontSize" Value="13"/>
        <Setter Property="FontWeight" Value="Bold"/>
        <Setter Property="CharacterSpacing" Value="50"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextMutedBrush}"/>
    </Style>

    <!-- Section Title: Syne 13px, Bold -->
    <Style x:Key="PotomacSectionTitle" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
        <Setter Property="FontSize" Value="13"/>
        <Setter Property="FontWeight" Value="Bold"/>
        <Setter Property="CharacterSpacing" Value="-10"/>
    </Style>

    <!-- Mono Label -->
    <Style x:Key="PotomacMonoLabel" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource DMMonoFont}"/>
        <Setter Property="FontSize" Value="9"/>
        <Setter Property="CharacterSpacing" Value="5"/>
    </Style>

    <!-- Stat Number: DM Mono 40px -->
    <Style x:Key="PotomacStatNumber" TargetType="TextBlock">
        <Setter Property="FontFamily" Value="{StaticResource DMMonoFont}"/>
        <Setter Property="FontSize" Value="40"/>
        <Setter Property="FontWeight" Value="Normal"/>
        <Setter Property="CharacterSpacing" Value="-30"/>
        <Setter Property="Foreground" Value="{ThemeResource PotomacTextBrush}"/>
    </Style>
</ResourceDictionary>
```

---

## 3. Color System

### Accent Color Picker

```xml
<!-- Controls/AccentColorPicker.xaml -->
<UserControl x:Class="AnalystApp.Controls.AccentColorPicker">

    <StackPanel Orientation="Horizontal" Spacing="12">
        <Button Style="{StaticResource PotomacColorSwatchButton}"
                Tag="#FEC00F" Click="AccentColor_Click">
            <Ellipse Width="36" Height="36" Fill="#FEC00F"/>
        </Button>
        <Button Style="{StaticResource PotomacColorSwatchButton}"
                Tag="#60A5FA" Click="AccentColor_Click">
            <Ellipse Width="36" Height="36" Fill="#60A5FA"/>
        </Button>
        <Button Style="{StaticResource PotomacColorSwatchButton}"
                Tag="#34D399" Click="AccentColor_Click">
            <Ellipse Width="36" Height="36" Fill="#34D399"/>
        </Button>
        <Button Style="{StaticResource PotomacColorSwatchButton}"
                Tag="#A78BFA" Click="AccentColor_Click">
            <Ellipse Width="36" Height="36" Fill="#A78BFA"/>
        </Button>
        <Button Style="{StaticResource PotomacColorSwatchButton}"
                Tag="#FB923C" Click="AccentColor_Click">
            <Ellipse Width="36" Height="36" Fill="#FB923C"/>
        </Button>
        <Button Style="{StaticResource PotomacColorSwatchButton}"
                Tag="#EC4899" Click="AccentColor_Click">
            <Ellipse Width="36" Height="36" Fill="#EC4899"/>
        </Button>
    </StackPanel>
</UserControl>
```

```csharp
// Controls/AccentColorPicker.xaml.cs
public sealed partial class AccentColorPicker : UserControl
{
    public event EventHandler<Color>? AccentColorChanged;

    private void AccentColor_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string hex)
        {
            var color = ColorHelper(hex);
            AccentColorChanged?.Invoke(this, color);
        }
    }

    private static Color ColorHelper(string hex)
    {
        hex = hex.TrimStart('#');
        return Color.FromArgb(
            255,
            byte.Parse(hex[..2], System.Globalization.NumberStyles.HexNumber),
            byte.Parse(hex[2..4], System.Globalization.NumberStyles.HexNumber),
            byte.Parse(hex[4..6], System.Globalization.NumberStyles.HexNumber)
        );
    }
}
```

---

## 4. Dark & Light Theme

### Theme Service

```csharp
// Services/ThemeService.cs
using Microsoft.UI.Xaml;
using Windows.Storage;

namespace AnalystApp.Services;

public enum ThemeMode { Light, Dark, System }

public class ThemeService
{
    private const string ThemeKey = "theme_mode";
    private readonly Application _app;

    public ThemeService(Application app)
    {
        _app = app;
    }

    public ThemeMode CurrentTheme
    {
        get
        {
            var saved = ApplicationData.Current.LocalSettings.Values[ThemeKey] as string;
            return Enum.TryParse<ThemeMode>(saved, out var mode) ? mode : ThemeMode.System;
        }
    }

    public void SetTheme(ThemeMode mode)
    {
        ApplicationData.Current.LocalSettings.Values[ThemeKey] = mode.ToString();
        ApplyTheme(mode);
    }

    public void ApplyTheme(ThemeMode mode)
    {
        var root = _app.Resources.MergedDictionaries;

        // Remove existing theme dictionaries
        for (int i = root.Count - 1; i >= 0; i--)
        {
            if (root[i].Source?.OriginalString.Contains("Dark") == true ||
                root[i].Source?.OriginalString.Contains("Light") == true)
            {
                root.RemoveAt(i);
            }
        }

        // Apply new theme
        var isDark = mode == ThemeMode.Dark ||
            (mode == ThemeMode.System && IsSystemDark());

        var themeFile = isDark ? "Themes/DarkTheme.xaml" : "Themes/LightTheme.xaml";
        root.Add(new ResourceDictionary
        {
            Source = new Uri($"ms-appx:///{themeFile}")
        });

        // Update accent brushes
        UpdateAccentBrushes(GetCurrentAccentColor());
    }

    private static bool IsSystemDark()
    {
        var settings = new Windows.UI.ViewManagement.UISettings();
        var bg = settings.GetColorValue(
            Windows.UI.ViewManagement.UIColorType.Background);
        return bg.R < 128;
    }

    public void UpdateAccentBrushes(Color accent)
    {
        _app.Resources["PotomacAccentBrush"] = new SolidColorBrush(accent);
        _app.Resources["PotomacAccentDimBrush"] = new SolidColorBrush(
            Color.FromArgb(0x14, accent.R, accent.G, accent.B));
        _app.Resources["PotomacAccentBorderBrush"] = new SolidColorBrush(
            Color.FromArgb(0x2E, accent.R, accent.G, accent.B));
    }

    public Color GetCurrentAccentColor()
    {
        return (Color)_app.Resources["PotomacAccentColor"];
    }
}
```

### Top Accent Bar

```xml
<!-- In MainWindow or each Page: -->
<Rectangle Height="1" HorizontalAlignment="Stretch" Margin="0,0,0,0">
    <Rectangle.Fill>
        <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
            <GradientStop Color="Transparent" Offset="0"/>
            <GradientStop Color="{ThemeResource PotomacAccentColor}" Offset="0.4"/>
            <GradientStop Color="#1EFEC00F" Offset="0.6"/>
            <GradientStop Color="Transparent" Offset="1"/>
        </LinearGradientBrush>
    </Rectangle.Fill>
</Rectangle>
```

---

## 5. Theme Styles

### Theme Style Picker

```xml
<!-- Controls/ThemeStylePicker.xaml -->
<UserControl x:Class="AnalystApp.Controls.ThemeStylePicker">

    <ItemsControl ItemsSource="{x:Bind ThemeStyles}">
        <ItemsControl.ItemsPanel>
            <ItemsPanelTemplate>
                <ItemsWrapGrid MaximumRowsOrColumns="3"/>
            </ItemsPanelTemplate>
        </ItemsControl.ItemsPanel>

        <ItemsControl.ItemTemplate>
            <DataTemplate x:DataType="local:ThemeStyleOption">
                <Button Style="{StaticResource PotomacThemeStyleCard}"
                        Click="ThemeStyle_Click" Tag="{x:Bind Value}">
                    <StackPanel Spacing="10" Padding="20" HorizontalAlignment="Center">
                        <Border Width="44" Height="44" CornerRadius="12"
                                Background="{x:Bind AccentDim}">
                            <FontIcon Glyph="{x:Bind IconGlyph}"
                                      FontSize="20" Foreground="{x:Bind Accent}"/>
                        </Border>

                        <TextBlock Text="{x:Bind DisplayName}"
                                   Style="{StaticResource PotomacSectionTitle}"
                                   HorizontalAlignment="Center"/>
                        <TextBlock Text="{x:Bind Description}"
                                   Style="{StaticResource PotomacMonoLabel}"
                                   Foreground="{ThemeResource PotomacTextMutedBrush}"
                                   HorizontalAlignment="Center"/>
                    </StackPanel>
                </Button>
            </DataTemplate>
        </ItemsControl.ItemTemplate>
    </ItemsControl>
</UserControl>
```

---

## 6. Spacing & Layout

### Page Template

```xml
<!-- Controls/PotomacPage.xaml -->
<UserControl x:Class="AnalystApp.Controls.PotomacPage">

    <ScrollViewer VerticalScrollBarVisibility="Auto"
                  HorizontalScrollBarVisibility="Disabled">
        <Grid MaxWidth="{StaticResource PotomacMaxContentWidth}"
              HorizontalAlignment="Stretch">

            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
            </Grid.RowDefinitions>

            <!-- Accent bar -->
            <Rectangle Grid.Row="0" Height="1">
                <Rectangle.Fill>
                    <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
                        <GradientStop Color="Transparent" Offset="0"/>
                        <GradientStop Color="{ThemeResource PotomacAccentColor}" Offset="0.4"/>
                        <GradientStop Color="#1EFEC00F" Offset="0.6"/>
                        <GradientStop Color="Transparent" Offset="1"/>
                    </LinearGradientBrush>
                </Rectangle.Fill>
            </Rectangle>

            <!-- Page content -->
            <ContentPresenter Grid.Row="2"
                              Content="{TemplateBinding PageContent}"
                              Padding="{StaticResource PotomacPagePadding}"/>
        </Grid>
    </ScrollViewer>
</UserControl>
```

### Section Header

```xml
<!-- Controls/SectionHeader.xaml -->
<UserControl x:Class="AnalystApp.Controls.SectionHeader">

    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>

        <!-- Accent bar -->
        <Border Grid.Column="0" Width="3" Height="16"
                CornerRadius="3">
            <Border.Background>
                <LinearGradientBrush StartPoint="0,0" EndPoint="0,1">
                    <GradientStop Color="{ThemeResource PotomacAccentColor}" Offset="0"/>
                    <GradientStop Color="#33FEC00F" Offset="1"/>
                </LinearGradientBrush>
            </Border.Background>
        </Border>

        <!-- Label -->
        <TextBlock Grid.Column="1" Text="{x:Bind Label}"
                   Style="{StaticResource PotomacEyebrowLabel}"
                   Margin="16,0,0,0"/>

        <!-- Divider -->
        <Rectangle Grid.Column="2" Height="1"
                   Fill="{ThemeResource PotomacBorderBrush}"
                   Margin="16,0,0,0"/>

        <!-- Action link -->
        <Button Grid.Column="3" Content="{x:Bind ActionText}"
                Style="{StaticResource PotomacTextButtonStyle}"
                Visibility="{x:Bind HasAction}"
                Click="Action_Click" Margin="16,0,0,0"/>
    </Grid>
</UserControl>
```

---

## 7. Component Library

### Card

```xml
<!-- Styles/PotomacControls.xaml -->
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">

    <Style x:Key="PotomacCard" TargetType="Border">
        <Setter Property="Background" Value="{ThemeResource PotomacCardBrush}"/>
        <Setter Property="BorderBrush" Value="{ThemeResource PotomacBorderBrush}"/>
        <Setter Property="BorderThickness" Value="1"/>
        <Setter Property="CornerRadius" Value="{StaticResource PotomacCornerRadius}"/>
        <Setter Property="Padding" Value="{StaticResource PotomacCardPadding}"/>
        <Setter Property="Margin" Value="{StaticResource PotomacCardMargin}"/>
    </Style>

    <Style x:Key="PotomacCardAccent" TargetType="Border">
        <Setter Property="Background" Value="{ThemeResource PotomacCardBrush}"/>
        <Setter Property="BorderBrush" Value="{ThemeResource PotomacBorderBrush}"/>
        <Setter Property="BorderThickness" Value="1"/>
        <Setter Property="CornerRadius" Value="{StaticResource PotomacCornerRadius}"/>
        <Setter Property="Padding" Value="{StaticResource PotomacCardPadding}"/>
    </Style>
</ResourceDictionary>
```

### Primary Button

```xml
<Style x:Key="PotomacPrimaryButton" TargetType="Button">
    <Setter Property="Background" Value="{ThemeResource PotomacAccentBrush}"/>
    <Setter Property="Foreground" Value="#09090B"/>
    <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
    <Setter Property="FontSize" Value="12"/>
    <Setter Property="FontWeight" Value="Bold"/>
    <Setter Property="CharacterSpacing" Value="80"/>
    <Setter Property="CornerRadius" Value="10"/>
    <Setter Property="Padding" Value="32,15"/>
    <Setter Property="HorizontalContentAlignment" Value="Center"/>
    <Setter Property="VerticalContentAlignment" Value="Center"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Grid x:Name="RootGrid"
                      Background="{TemplateBinding Background}"
                      CornerRadius="{TemplateBinding CornerRadius}"
                      Padding="{TemplateBinding Padding}">
                    <Grid.RenderTransform>
                        <TranslateTransform x:Name="ButtonTranslate" Y="0"/>
                    </Grid.RenderTransform>

                    <ContentPresenter
                        HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}"
                        VerticalAlignment="{TemplateBinding VerticalContentAlignment}"/>

                    <VisualStateManager.VisualStateGroups>
                        <VisualStateGroup x:Name="CommonStates">
                            <VisualState x:Name="Normal">
                                <Storyboard>
                                    <DoubleAnimation
                                        Storyboard.TargetName="ButtonTranslate"
                                        Storyboard.TargetProperty="Y"
                                        To="0" Duration="0:0:0.2"/>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="PointerOver">
                                <Storyboard>
                                    <DoubleAnimation
                                        Storyboard.TargetName="ButtonTranslate"
                                        Storyboard.TargetProperty="Y"
                                        To="-2" Duration="0:0:0.2"/>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="Pressed">
                                <Storyboard>
                                    <DoubleAnimation
                                        Storyboard.TargetName="ButtonTranslate"
                                        Storyboard.TargetProperty="Y"
                                        To="0" Duration="0:0:0.1"/>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="Disabled">
                                <VisualState.Setters>
                                    <Setter Target="RootGrid.Opacity" Value="0.5"/>
                                </VisualState.Setters>
                            </VisualState>
                        </VisualStateGroup>
                    </VisualStateManager.VisualStateGroups>
                </Grid>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### Secondary Button

```xml
<Style x:Key="PotomacSecondaryButton" TargetType="Button">
    <Setter Property="Background" Value="{ThemeResource PotomacCardBrush}"/>
    <Setter Property="Foreground" Value="{ThemeResource PotomacTextBrush}"/>
    <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
    <Setter Property="FontSize" Value="12"/>
    <Setter Property="FontWeight" Value="Bold"/>
    <Setter Property="CharacterSpacing" Value="60"/>
    <Setter Property="CornerRadius" Value="10"/>
    <Setter Property="Padding" Value="28,15"/>
    <Setter Property="BorderBrush" Value="{ThemeResource PotomacBorderBrush}"/>
    <Setter Property="BorderThickness" Value="1"/>
</Style>
```

### Text Field

```xml
<Style x:Key="PotomacTextBox" TargetType="TextBox">
    <Setter Property="Background" Value="{ThemeResource PotomacRaisedBrush}"/>
    <Setter Property="Foreground" Value="{ThemeResource PotomacTextBrush}"/>
    <Setter Property="BorderBrush" Value="{ThemeResource PotomacBorderBrush}"/>
    <Setter Property="BorderThickness" Value="1"/>
    <Setter Property="CornerRadius" Value="10"/>
    <Setter Property="Padding" Value="16,12"/>
    <Setter Property="Height" Value="46"/>
    <Setter Property="FontFamily" Value="{StaticResource InstrumentSansFont}"/>
    <Setter Property="FontSize" Value="14"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="TextBox">
                <Grid>
                    <Border x:Name="BorderElement"
                            Background="{TemplateBinding Background}"
                            BorderBrush="{TemplateBinding BorderBrush}"
                            BorderThickness="{TemplateBinding BorderThickness}"
                            CornerRadius="{TemplateBinding CornerRadius}">

                        <Grid>
                            <ScrollViewer x:Name="ContentElement"
                                          Padding="{TemplateBinding Padding}"
                                          HorizontalScrollBarVisibility="Hidden"
                                          VerticalScrollBarVisibility="Hidden"/>
                            <TextBlock x:Name="PlaceholderText"
                                       Text="{TemplateBinding PlaceholderText}"
                                       Foreground="{ThemeResource PotomacTextMutedBrush}"
                                       Padding="{TemplateBinding Padding}"
                                       VerticalAlignment="Center"
                                       FontFamily="{TemplateBinding FontFamily}"
                                       FontSize="{TemplateBinding FontSize}"/>
                        </Grid>
                    </Border>

                    <VisualStateManager.VisualStateGroups>
                        <VisualStateGroup x:Name="CommonStates">
                            <VisualState x:Name="Normal"/>
                            <VisualState x:Name="PointerOver">
                                <VisualState.Setters>
                                    <Setter Target="BorderElement.BorderBrush"
                                            Value="{ThemeResource PotomacAccentBorderBrush}"/>
                                </VisualState.Setters>
                            </VisualState>
                            <VisualState x:Name="Focused">
                                <VisualState.Setters>
                                    <Setter Target="BorderElement.BorderBrush"
                                            Value="{ThemeResource PotomacAccentBrush}"/>
                                </VisualState.Setters>
                            </VisualState>
                        </VisualStateGroup>
                    </VisualStateManager.VisualStateGroups>
                </Grid>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### Toggle Switch

```xml
<Style x:Key="PotomacToggleSwitch" TargetType="ToggleSwitch">
    <Setter Property="MinWidth" Value="48"/>
    <Setter Property="OnContent" Value=""/>
    <Setter Property="OffContent" Value=""/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="ToggleSwitch">
                <Grid>
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="Auto"/>
                    </Grid.ColumnDefinitions>

                    <StackPanel Grid.Column="0" VerticalAlignment="Center">
                        <TextBlock Text="{TemplateBinding Header}"
                                   Style="{StaticResource PotomacSectionTitle}"/>
                        <TextBlock Text="{TemplateBinding OffContent}"
                                   Style="{StaticResource PotomacBodyMuted}"/>
                    </StackPanel>

                    <Border x:Name="SwitchKnob" Grid.Column="1"
                            Width="48" Height="26" CornerRadius="13"
                            Background="#D1D5DB" Margin="16,0,0,0">
                        <Ellipse x:Name="Knob" Width="20" Height="20"
                                 Fill="White" HorizontalAlignment="Left"
                                 Margin="3,0,0,0"/>
                    </Border>
                </Grid>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### Badge

```xml
<Style x:Key="PotomacBadge" TargetType="Border">
    <Setter Property="Background" Value="{ThemeResource PotomacAccentBrush}"/>
    <Setter Property="CornerRadius" Value="100"/>
    <Setter Property="Padding" Value="8,2"/>
</Style>
```

### Stat Card

```xml
<Border Style="{StaticResource PotomacCard}">
    <Border CornerRadius="14" Style="{StaticResource PotomacCard}">
        <StackPanel>
            <TextBlock Text="{x:Bind Label}" Style="{StaticResource PotomacMonoLabel}"
                       Foreground="{ThemeResource PotomacTextMutedBrush}"/>
            <TextBlock Text="{x:Bind Value}" Style="{StaticResource PotomacStatNumber}"/>
        </StackPanel>
    </Border>
</Border>
```

---

## 8. Navigation

### Sidebar Navigation

```xml
<!-- Controls/PotomacSidebar.xaml -->
<UserControl x:Class="AnalystApp.Controls.PotomacSidebar"
             xmlns:muxc="using:Microsoft.UI.Xaml.Controls">

    <Grid Width="{StaticResource PotomacSidebarWidth}"
          Background="{ThemeResource PotomacSidebarBrush}">

        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- Logo Section -->
        <Grid Grid.Row="0" Height="88" Padding="20,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="Auto"/>
            </Grid.ColumnDefinitions>

            <Border Grid.Column="0" Width="44" Height="44" CornerRadius="14"
                    Background="{ThemeResource PotomacAccentDimBrush}">
                <Image Source="/Assets/potomac-icon.png" Width="44" Height="44"/>
            </Border>

            <StackPanel Grid.Column="1" VerticalAlignment="Center" Margin="12,0,0,0">
                <TextBlock Text="ANALYST"
                           FontFamily="{StaticResource SyneFont}"
                           FontSize="20" FontWeight="ExtraBold"
                           CharacterSpacing="200"/>
                <StackPanel Orientation="Horizontal" Spacing="5">
                    <Ellipse Width="5" Height="5" Fill="{ThemeResource PotomacWarningColor}"/>
                    <TextBlock Text="DEVELOPER BETA"
                               Style="{StaticResource PotomacMonoLabel}"
                               Foreground="{ThemeResource PotomacWarningColor}"
                               FontSize="8" CharacterSpacing="14"/>
                </StackPanel>
            </StackPanel>

            <Button Grid.Column="2" Content="&#xE76B;"
                    FontFamily="{StaticResource SymbolThemeFontFamily}"
                    Style="{StaticResource PotomacIconButtonStyle}"/>
        </Grid>

        <!-- Navigation Items -->
        <ScrollViewer Grid.Row="1" Padding="16,24">
            <StackPanel Spacing="8">
                <Button x:Name="NavDashboard" Tag="Dashboard"
                        Style="{StaticResource PotomacNavButton}"
                        Click="NavButton_Click">
                    <StackPanel Orientation="Horizontal" Spacing="16">
                        <Border Width="36" Height="36" CornerRadius="10"
                                Background="{ThemeResource PotomacBlueDimBrush}">
                            <FontIcon Glyph="&#xE80F;" FontSize="18"
                                      Foreground="{ThemeResource PotomacBlueColor}"/>
                        </Border>
                        <TextBlock Text="DASHBOARD" Style="{StaticResource PotomacNavLabel}"
                                   VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>

                <Button x:Name="NavAFL" Tag="AFL"
                        Style="{StaticResource PotomacNavButton}"
                        Click="NavButton_Click">
                    <StackPanel Orientation="Horizontal" Spacing="16">
                        <Border Width="36" Height="36" CornerRadius="10"
                                Background="{ThemeResource PotomacBlueDimBrush}">
                            <FontIcon Glyph="&#xE943;" FontSize="18"
                                      Foreground="{ThemeResource PotomacBlueColor}"/>
                        </Border>
                        <TextBlock Text="AFL GENERATOR" Style="{StaticResource PotomacNavLabel}"
                                   VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>

                <Button x:Name="NavChat" Tag="Chat"
                        Style="{StaticResource PotomacNavButton}"
                        Click="NavButton_Click">
                    <StackPanel Orientation="Horizontal" Spacing="16">
                        <Border Width="36" Height="36" CornerRadius="10"
                                Background="{ThemeResource PotomacBlueDimBrush}">
                            <FontIcon Glyph="&#xE8F2;" FontSize="18"
                                      Foreground="{ThemeResource PotomacBlueColor}"/>
                        </Border>
                        <TextBlock Text="CHAT" Style="{StaticResource PotomacNavLabel}"
                                   VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>

                <Button x:Name="NavKB" Tag="Knowledge"
                        Style="{StaticResource PotomacNavButton}"
                        Click="NavButton_Click">
                    <StackPanel Orientation="Horizontal" Spacing="16">
                        <Border Width="36" Height="36" CornerRadius="10"
                                Background="{ThemeResource PotomacBlueDimBrush}">
                            <FontIcon Glyph="&#xE8F1;" FontSize="18"
                                      Foreground="{ThemeResource PotomacBlueColor}"/>
                        </Border>
                        <TextBlock Text="KNOWLEDGE BASE" Style="{StaticResource PotomacNavLabel}"
                                   VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>

                <Button x:Name="NavSettings" Tag="Settings"
                        Style="{StaticResource PotomacNavButton}"
                        Click="NavButton_Click">
                    <StackPanel Orientation="Horizontal" Spacing="16">
                        <Border Width="36" Height="36" CornerRadius="10"
                                Background="{ThemeResource PotomacBlueDimBrush}">
                            <FontIcon Glyph="&#xE713;" FontSize="18"
                                      Foreground="{ThemeResource PotomacBlueColor}"/>
                        </Border>
                        <TextBlock Text="SETTINGS" Style="{StaticResource PotomacNavLabel}"
                                   VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>
            </StackPanel>
        </ScrollViewer>

        <!-- User Section -->
        <Grid Grid.Row="2" Padding="24">
            <StackPanel>
                <Grid Margin="0,0,0,20">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>

                    <Ellipse Grid.Column="0" Width="48" Height="48">
                        <Ellipse.Fill>
                            <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
                                <GradientStop Color="#60A5FA" Offset="0"/>
                                <GradientStop Color="#A78BFA" Offset="1"/>
                            </LinearGradientBrush>
                        </Ellipse.Fill>
                    </Ellipse>

                    <StackPanel Grid.Column="1" VerticalAlignment="Center" Margin="16,0,0,0">
                        <TextBlock Text="{x:Bind UserName}"
                                   Style="{StaticResource PotomacBody}"/>
                        <TextBlock Text="{x:Bind UserEmail}"
                                   Style="{StaticResource PotomacMonoLabel}"/>
                    </StackPanel>
                </Grid>

                <Button Content="LOGOUT" Style="{StaticResource PotomacDestructiveButton}"
                        HorizontalAlignment="Stretch" Click="Logout_Click"/>
            </StackPanel>
        </Grid>
    </Grid>
</UserControl>
```

### Selected Nav Button Style

```xml
<Style x:Key="PotomacNavButton" TargetType="Button">
    <Setter Property="Background" Value="Transparent"/>
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="Padding" Value="16,14"/>
    <Setter Property="HorizontalAlignment" Value="Stretch"/>
    <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
    <Setter Property="CornerRadius" Value="14"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Border x:Name="RootBorder"
                        Background="{TemplateBinding Background}"
                        CornerRadius="{TemplateBinding CornerRadius}"
                        Padding="{TemplateBinding Padding}">
                    <ContentPresenter/>
                </Border>

                <VisualStateManager.VisualStateGroups>
                    <VisualStateGroup x:Name="CommonStates">
                        <VisualState x:Name="Normal"/>
                        <VisualState x:Name="PointerOver">
                            <VisualState.Setters>
                                <Setter Target="RootBorder.Background"
                                        Value="{ThemeResource PotomacAccentDimBrush}"/>
                            </VisualState.Setters>
                        </VisualState>
                        <VisualState x:Name="Pressed"/>
                        <VisualState x:Name="Selected">
                            <VisualState.Setters>
                                <Setter Target="RootBorder.Background">
                                    <Setter.Value>
                                        <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
                                            <GradientStop Color="#60A5FA" Offset="0"/>
                                            <GradientStop Color="#A78BFA" Offset="1"/>
                                        </LinearGradientBrush>
                                    </Setter.Value>
                                </Setter>
                            </VisualState.Setters>
                        </VisualState>
                    </VisualStateGroup>
                </VisualStateManager.VisualStateGroups>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### MainWindow

```xml
<!-- MainWindow.xaml -->
<Window x:Class="AnalystApp.MainWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:local="using:AnalystApp.Controls"
        Title="Analyst by Potomac"
        BackdropMaterial="Mica">

    <Grid Background="{ThemeResource PotomacBackgroundBrush}">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>

        <!-- Sidebar -->
        <local:PotomacSidebar x:Name="Sidebar" Grid.Column="0"
                              NavigationInvoked="Sidebar_NavigationInvoked"/>

        <!-- Content -->
        <Frame x:Name="ContentFrame" Grid.Column="1"/>
    </Grid>
</Window>
```

```csharp
// MainWindow.xaml.cs
public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        // Extend title bar
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        // Navigate to dashboard on load
        ContentFrame.Navigate(typeof(DashboardPage));
    }

    private void Sidebar_NavigationInvoked(string pageName)
    {
        var pageType = pageName switch
        {
            "Dashboard" => typeof(DashboardPage),
            "AFL" => typeof(AflGeneratorPage),
            "Chat" => typeof(ChatPage),
            "Knowledge" => typeof(KnowledgeBasePage),
            "Settings" => typeof(SettingsPage),
            _ => typeof(DashboardPage)
        };

        ContentFrame.Navigate(pageType);
    }
}
```

---

## 9. Login & Register

### Login Page

```xml
<!-- Views/LoginPage.xaml -->
<Page x:Class="AnalystApp.Views.LoginPage"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="520"/>
        </Grid.ColumnDefinitions>

        <!-- ═══ BRANDING PANEL ═══ -->
        <Grid Grid.Column="0">
            <Grid.Background>
                <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
                    <GradientStop Color="#0A0A0B" Offset="0"/>
                    <GradientStop Color="#0D1117" Offset="0.5"/>
                    <GradientStop Color="#0A0A0B" Offset="1"/>
                </LinearGradientBrush>
            </Grid.Background>

            <!-- Grid pattern -->
            <Canvas Opacity="0.04">
                <Rectangle Canvas.Left="0" Canvas.Top="0"
                           Width="40" Height="40" Stroke="#60A5FA"
                           StrokeThickness="0.5"/>
            </Canvas>

            <StackPanel VerticalAlignment="Center" HorizontalAlignment="Center">
                <!-- Logo -->
                <Border Width="110" Height="110" CornerRadius="28"
                        HorizontalAlignment="Center"
                        Background="#14FEC00F">
                    <Border.Effect>
                        <DropShadowEffect Color="#FEC00F" BlurRadius="8" ShadowDepth="0"/>
                    </Border.Effect>
                    <Image Source="/Assets/potomac-icon.png" Width="70" Height="70"/>
                </Border>

                <TextBlock Text="ANALYST" HorizontalAlignment="Center"
                           Margin="0,24,0,0">
                    <TextBlock.Style>
                        <Style TargetType="TextBlock">
                            <Setter Property="FontFamily" Value="{StaticResource SyneFont}"/>
                            <Setter Property="FontSize" Value="52"/>
                            <Setter Property="FontWeight" Value="ExtraBold"/>
                        </Style>
                    </TextBlock.Style>
                </TextBlock>

                <TextBlock Text="BY POTOMAC" HorizontalAlignment="Center"
                           FontSize="17" FontWeight="Bold"
                           Foreground="{ThemeResource PotomacAccentBrush}"
                           Margin="0,8,0,36"/>

                <!-- Tagline box -->
                <Border CornerRadius="16" Padding="44,32"
                        Background="#14FEC00F"
                        BorderBrush="#40FEC00F" BorderThickness="1"
                        HorizontalAlignment="Center">
                    <Border.Effect>
                        <DropShadowEffect Color="#FEC00F" BlurRadius="8" ShadowDepth="0"/>
                    </Border.Effect>

                    <StackPanel>
                        <Border Height="2" Margin="0,0,0,16">
                            <Border.Background>
                                <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
                                    <GradientStop Color="Transparent" Offset="0"/>
                                    <GradientStop Color="#FEC00F" Offset="0.5"/>
                                    <GradientStop Color="Transparent" Offset="1"/>
                                </LinearGradientBrush>
                            </Border.Background>
                        </Border>

                        <TextBlock Text="BREAK THE STATUS QUO"
                                   FontSize="30" FontWeight="ExtraBold"
                                   Foreground="{ThemeResource PotomacAccentBrush}"
                                   TextAlignment="Center" CharacterSpacing="14"/>

                        <Border Height="2" Margin="0,16,0,0">
                            <Border.Background>
                                <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
                                    <GradientStop Color="Transparent" Offset="0"/>
                                    <GradientStop Color="#FEC00F" Offset="0.5"/>
                                    <GradientStop Color="Transparent" Offset="1"/>
                                </LinearGradientBrush>
                            </Border.Background>
                        </Border>
                    </StackPanel>
                </Border>
            </StackPanel>
        </Grid>

        <!-- ═══ FORM PANEL ═══ -->
        <Grid Grid.Column="1" Background="{ThemeResource PotomacCardBrush}"
              Padding="64,72">
            <StackPanel VerticalAlignment="Center" MaxWidth="380">
                <!-- Header -->
                <Grid Margin="0,0,0,28">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>

                    <Border Grid.Column="0" Width="40" Height="40" CornerRadius="12"
                            Background="#14FEC00F" Margin="0,0,16,0">
                        <FontIcon Glyph="&#xE771;" FontSize="18"
                                  Foreground="#60A5FA"/>
                    </Border>

                    <StackPanel Grid.Column="1" VerticalAlignment="Center">
                        <TextBlock Text="Welcome Back"
                                   FontSize="30" FontWeight="ExtraBold"/>
                        <TextBlock Text="Sign in to continue to your dashboard"
                                   Foreground="{ThemeResource PotomacTextMutedBrush}"
                                   Margin="0,6,0,0"/>
                    </StackPanel>
                </Grid>

                <!-- Email -->
                <TextBlock Text="EMAIL ADDRESS"
                           Style="{StaticResource PotomacEyebrowLabel}" Margin="0,0,0,10"/>
                <TextBox x:Name="EmailBox" PlaceholderText="you@example.com"
                         Style="{StaticResource PotomacTextBox}" Margin="0,0,0,24"/>

                <!-- Password -->
                <TextBlock Text="PASSWORD"
                           Style="{StaticResource PotomacEyebrowLabel}" Margin="0,0,0,10"/>
                <PasswordBox x:Name="PasswordBox" PlaceholderText="Enter your password"
                             Style="{StaticResource PotomacPasswordBox}" Margin="0,0,0,8"/>

                <Button Content="Forgot password?"
                        Style="{StaticResource PotomacTextButtonStyle}"
                        HorizontalAlignment="Right" Margin="0,0,0,28"/>

                <!-- Sign In -->
                <Button x:Name="LoginButton" Content="SIGN IN"
                        Style="{StaticResource PotomacPrimaryButton}"
                        HorizontalAlignment="Stretch" Margin="0,0,0,36"
                        Click="LoginButton_Click"/>

                <!-- Divider -->
                <Grid Margin="0,0,0,36">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>

                    <Rectangle Grid.Column="0" Height="1"
                               Fill="{ThemeResource PotomacBorderBrush}"/>
                    <TextBlock Grid.Column="1" Text="OR" Margin="16,0"
                               Style="{StaticResource PotomacMonoLabel}"/>
                    <Rectangle Grid.Column="2" Height="1"
                               Fill="{ThemeResource PotomacBorderBrush}"/>
                </Grid>

                <!-- Sign Up -->
                <TextBlock Text="Don't have an account?"
                           HorizontalAlignment="Center" Margin="0,0,0,8"/>
                <Button Content="CREATE ONE"
                        Style="{StaticResource PotomacSecondaryButton}"
                        HorizontalAlignment="Center"
                        Click="GoToRegister_Click"/>
            </StackPanel>
        </Grid>
    </Grid>
</Page>
```

---

## 10. Dashboard

### Dashboard View

```xml
<!-- Views/DashboardPage.xaml -->
<Page x:Class="AnalystApp.Views.DashboardPage"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <ScrollViewer Padding="52,56" VerticalScrollBarVisibility="Auto">
        <StackPanel MaxWidth="1360">

            <!-- ═══ HERO SECTION ═══ -->
            <Border Style="{StaticResource PotomacCard}" Margin="0,0,0,52">
                <StackPanel>
                    <!-- Eyebrow -->
                    <Border HorizontalAlignment="Left" CornerRadius="100"
                            Padding="14,5" Background="#14FEC00F"
                            BorderBrush="#33FEC00F" BorderThickness="1">
                        <StackPanel Orientation="Horizontal" Spacing="10">
                            <Ellipse Width="5" Height="5" Fill="#FEC00F"/>
                            <TextBlock Text="Trading Platform · Live"
                                       Style="{StaticResource PotomacMonoLabel}"
                                       Foreground="#FEC00F" FontSize="9.5"/>
                        </StackPanel>
                    </Border>

                    <TextBlock Margin="0,24,0,0">
                        <Run Text="Good morning, " FontSize="52" FontWeight="ExtraBold"/>
                        <Run Text="Trader" FontSize="52" FontWeight="ExtraBold"
                             Foreground="{ThemeResource PotomacAccentBrush}"/>
                    </TextBlock>

                    <TextBlock Text="Your edge starts here."
                               FontSize="28" Foreground="{ThemeResource PotomacTextMutedBrush}"
                               Margin="0,6,0,20"/>

                    <TextBlock Style="{StaticResource PotomacBodyMuted}" Margin="0,0,0,36">
                        AI-powered AFL generation, strategy analysis, and intelligent
                        trading tools — purpose-built for systematic traders.
                    </TextBlock>

                    <StackPanel Orientation="Horizontal" Spacing="12">
                        <Button Content="GENERATE AFL" Style="{StaticResource PotomacPrimaryButton}"/>
                        <Button Content="OPEN CHAT" Style="{StaticResource PotomacSecondaryButton}"/>
                    </StackPanel>
                </StackPanel>
            </Border>

            <!-- ═══ FEATURE CARDS ═══ -->
            <TextBlock Text="PLATFORM TOOLS" Style="{StaticResource PotomacEyebrowLabel}"
                       Margin="0,0,0,20"/>

            <GridView ItemsSource="{x:Bind Features}" SelectionMode="None">
                <GridView.ItemTemplate>
                    <DataTemplate x:DataType="local:FeatureItem">
                        <Border Width="280" CornerRadius="20" Padding="28"
                                Background="{ThemeResource PotomacCardBrush}"
                                BorderBrush="{ThemeResource PotomacBorderBrush}"
                                BorderThickness="1">
                            <StackPanel>
                                <Grid Margin="0,0,0,24">
                                    <Border Width="52" Height="52" CornerRadius="14"
                                            Background="{x:Bind AccentDim}"
                                            BorderBrush="{x:Bind AccentBorder}" BorderThickness="1">
                                        <FontIcon Glyph="{x:Bind Icon}" FontSize="22"
                                                  Foreground="{x:Bind Accent}"/>
                                    </Border>
                                </Grid>

                                <TextBlock Text="{x:Bind Title}"
                                           FontSize="16" FontWeight="ExtraBold"/>
                                <TextBlock Text="{x:Bind Description}"
                                           Style="{StaticResource PotomacBodyMuted}"
                                           Margin="0,10,0,22"/>

                                <Border CornerRadius="10" Padding="14,8"
                                        Background="{x:Bind AccentDim}"
                                        BorderBrush="{x:Bind AccentBorder}" BorderThickness="1">
                                    <StackPanel Orientation="Horizontal" Spacing="8">
                                        <TextBlock Text="Launch"
                                                   FontFamily="{StaticResource DMMonoFont}"
                                                   FontSize="10" FontWeight="SemiBold"
                                                   Foreground="{x:Bind Accent}"/>
                                    </StackPanel>
                                </Border>
                            </StackPanel>
                        </Border>
                    </DataTemplate>
                </GridView.ItemTemplate>
            </GridView>
        </StackPanel>
    </ScrollViewer>
</Page>
```

---

## 11. Chat Interface

### Chat View

```xml
<!-- Views/ChatPage.xaml -->
<Page x:Class="AnalystApp.Views.ChatPage">

    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- Messages -->
        <ScrollViewer Grid.Row="0" Padding="28,40"
                      VerticalScrollBarVisibility="Auto">
            <ItemsControl ItemsSource="{x:Bind Messages}">
                <ItemsControl.ItemTemplate>
                    <DataTemplate x:DataType="models:ChatMessage">
                        <Grid Margin="0,0,0,24">
                            <!-- User -->
                            <Grid Visibility="{x:Bind IsUser}" HorizontalAlignment="Right"
                                  MaxWidth="400">
                                <Border CornerRadius="16" Padding="12,16"
                                        Background="{ThemeResource PotomacAccentDimBrush}"
                                        BorderBrush="{ThemeResource PotomacAccentBorderBrush}"
                                        BorderThickness="1">
                                    <TextBlock Text="{x:Bind Content}" TextWrapping="Wrap"/>
                                </Border>
                            </Grid>

                            <!-- Assistant -->
                            <Grid Visibility="{x:Bind IsAssistant}" HorizontalAlignment="Left"
                                  MaxWidth="600">
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="Auto"/>
                                    <ColumnDefinition Width="*"/>
                                </Grid.ColumnDefinitions>

                                <Border Grid.Column="0" CornerRadius="10"
                                        Width="32" Height="32" Margin="0,0,12,0"
                                        Background="{ThemeResource PotomacBlueDimBrush}">
                                    <Image Source="/Assets/potomac-icon.png" Width="18" Height="18"/>
                                </Border>

                                <StackPanel Grid.Column="1">
                                    <TextBlock Text="Yang" FontWeight="Bold" Margin="0,0,0,6"/>
                                    <Border CornerRadius="16" Padding="14,18"
                                            Background="{ThemeResource PotomacAIBubbleBrush}"
                                            BorderBrush="{ThemeResource PotomacBorderBrush}"
                                            BorderThickness="1">
                                        <TextBlock Text="{x:Bind Content}" TextWrapping="Wrap"/>
                                    </Border>

                                    <!-- Action buttons -->
                                    <StackPanel Orientation="Horizontal" Spacing="4" Margin="0,6,0,0"
                                                Opacity="0">
                                        <Button Content="&#xE8C8;"
                                                FontFamily="{StaticResource SymbolThemeFontFamily}"
                                                Style="{StaticResource PotomacSmallIconButton}"/>
                                        <Button Content="&#xE8E1;"
                                                FontFamily="{StaticResource SymbolThemeFontFamily}"
                                                Style="{StaticResource PotomacSmallIconButton}"/>
                                        <Button Content="&#xE8E0;"
                                                FontFamily="{StaticResource SymbolThemeFontFamily}"
                                                Style="{StaticResource PotomacSmallIconButton}"/>
                                    </StackPanel>
                                </StackPanel>
                            </Grid>
                        </Grid>
                    </DataTemplate>
                </ItemsControl.ItemTemplate>
            </ItemsControl>
        </ScrollViewer>

        <!-- Input Bar -->
        <Grid Grid.Row="1" Padding="24,14"
              Background="{ThemeResource PotomacBackgroundBrush}">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <Rectangle Grid.Row="0" Height="1" Margin="0,0,0,12">
                <Rectangle.Fill>
                    <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
                        <GradientStop Color="Transparent" Offset="0"/>
                        <GradientStop Color="#60A5FA" Offset="0.4"/>
                        <GradientStop Color="#1E40AF" Offset="0.7"/>
                        <GradientStop Color="Transparent" Offset="1"/>
                    </LinearGradientBrush>
                </Rectangle.Fill>
            </Rectangle>

            <Grid Grid.Row="1">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>

                <Button Grid.Column="0" Content="&#xE7C3;"
                        FontFamily="{StaticResource SymbolThemeFontFamily}"
                        Style="{StaticResource PotomacIconButtonStyle}" Margin="0,0,12,0"/>

                <TextBox Grid.Column="1" PlaceholderText="Type a message..."
                         Style="{StaticResource PotomacTextBox}"
                         VerticalContentAlignment="Center"/>

                <Button Grid.Column="2" Content="&#xE7C7;"
                        FontFamily="{StaticResource SymbolThemeFontFamily}"
                        Style="{StaticResource PotomacAccentIconButtonStyle}" Margin="12,0,0,0"/>
            </Grid>
        </Grid>
    </Grid>
</Page>
```

---

## 12. AFL Generator

### AFL Generator View

```xml
<!-- Views/AflGeneratorPage.xaml -->
<Page x:Class="AnalystApp.Views.AflGeneratorPage">

    <ScrollViewer Padding="52,56" VerticalScrollBarVisibility="Auto">
        <StackPanel MaxWidth="1360">

            <!-- Eyebrow -->
            <Border HorizontalAlignment="Left" CornerRadius="100"
                    Padding="14,5" Background="#1460A5FA"
                    BorderBrush="#3360A5FA" BorderThickness="1">
                <StackPanel Orientation="Horizontal" Spacing="10">
                    <Ellipse Width="5" Height="5" Fill="#60A5FA"/>
                    <TextBlock Text="Code Generation · Ready"
                               Style="{StaticResource PotomacMonoLabel}"
                               Foreground="#60A5FA" FontSize="9.5"/>
                </StackPanel>
            </Border>

            <TextBlock Text="AFL Generator" Margin="0,24,0,8"
                       FontSize="52" FontWeight="ExtraBold" Foreground="#60A5FA"/>

            <TextBlock Style="{StaticResource PotomacBodyMuted}" Margin="0,0,0,40">
                Describe your trading strategy in plain language. The AI generates
                production-ready AmiBroker AFL code.
            </TextBlock>

            <!-- Prompt Card -->
            <Border Style="{StaticResource PotomacCard}">
                <StackPanel>
                    <controls:SectionHeader Label="STRATEGY DESCRIPTION"/>

                    <TextBox x:Name="PromptBox" Style="{StaticResource PotomacTextBox}"
                             Height="120" AcceptsReturn="True" TextWrapping="Wrap"
                             VerticalScrollBarVisibility="Auto"/>

                    <Grid Margin="0,16,0,0">
                        <TextBlock Text="{x:Bind PromptLength}"
                                   Style="{StaticResource PotomacMonoLabel}"/>
                        <Button Content="GENERATE" HorizontalAlignment="Right"
                                Style="{StaticResource PotomacPrimaryButton}"/>
                    </Grid>
                </StackPanel>
            </Border>

            <!-- Generated Code Card -->
            <Border Style="{StaticResource PotomacCard}" Margin="0,24,0,0"
                    Visibility="{x:Bind HasGeneratedCode}">
                <StackPanel>
                    <controls:SectionHeader Label="GENERATED AFL CODE"/>

                    <ScrollViewer HorizontalScrollBarVisibility="Auto"
                                  Background="{ThemeResource PotomacRaisedBrush}"
                                  CornerRadius="10" Padding="16">
                        <TextBlock Text="{x:Bind GeneratedCode}"
                                   FontFamily="{StaticResource DMMonoFont}"
                                   FontSize="12" TextWrapping="NoWrap"/>
                    </ScrollViewer>

                    <StackPanel Orientation="Horizontal" Spacing="12" Margin="0,16,0,0">
                        <Button Content="COPY" Style="{StaticResource PotomacSecondaryButton}"/>
                        <Button Content="OPTIMIZE" Style="{StaticResource PotomacSecondaryButton}"/>
                        <Button Content="DEBUG" Style="{StaticResource PotomacSecondaryButton}"/>
                    </StackPanel>
                </StackPanel>
            </Border>
        </StackPanel>
    </ScrollViewer>
</Page>
```

---

## 13. Knowledge Base

### Knowledge Base View

```xml
<!-- Views/KnowledgeBasePage.xaml -->
<Page x:Class="AnalystApp.Views.KnowledgeBasePage">

    <ScrollViewer Padding="52,56" VerticalScrollBarVisibility="Auto">
        <StackPanel MaxWidth="1360">

            <!-- Hero -->
            <Border HorizontalAlignment="Left" CornerRadius="100"
                    Padding="14,5" Background="#1434D399"
                    BorderBrush="#3334D399" BorderThickness="1">
                <StackPanel Orientation="Horizontal" Spacing="10">
                    <Ellipse Width="5" Height="5" Fill="#34D399"/>
                    <TextBlock Text="Knowledge Base · Indexed"
                               Style="{StaticResource PotomacMonoLabel}"
                               Foreground="#34D399" FontSize="9.5"/>
                </StackPanel>
            </Border>

            <TextBlock Text="Knowledge Base" Margin="0,24,0,8"
                       FontSize="52" FontWeight="ExtraBold" Foreground="#34D399"/>

            <!-- Stats -->
            <Grid Margin="0,0,0,52">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="*"/>
                </Grid.ColumnDefinitions>

                <Border Grid.Column="0" Style="{StaticResource PotomacCard}">
                    <StackPanel>
                        <TextBlock Text="Documents" Style="{StaticResource PotomacMonoLabel}"/>
                        <TextBlock Text="42" Style="{StaticResource PotomacStatNumber}"
                                   Foreground="#34D399"/>
                    </StackPanel>
                </Border>

                <Border Grid.Column="1" Style="{StaticResource PotomacCard}" Margin="16,0">
                    <StackPanel>
                        <TextBlock Text="Chunks" Style="{StaticResource PotomacMonoLabel}"/>
                        <TextBlock Text="500" Style="{StaticResource PotomacStatNumber}"
                                   Foreground="#60A5FA"/>
                    </StackPanel>
                </Border>

                <Border Grid.Column="2" Style="{StaticResource PotomacCard}">
                    <StackPanel>
                        <TextBlock Text="Size" Style="{StaticResource PotomacMonoLabel}"/>
                        <TextBlock Text="14.3 MB" Style="{StaticResource PotomacStatNumber}"
                                   Foreground="#A78BFA"/>
                    </StackPanel>
                </Border>
            </Grid>

            <!-- Upload Zone -->
            <Border Style="{StaticResource PotomacCard}" Background="#0C34D399"
                    BorderBrush="#6634D399" BorderThickness="2"
                    BorderDashArray="8,4" Height="120">
                <StackPanel VerticalAlignment="Center" HorizontalAlignment="Center">
                    <FontIcon Glyph="&#xE898;" FontSize="28" Foreground="#34D399"/>
                    <TextBlock Text="Drop files here or click to browse"
                               Style="{StaticResource PotomacBodyMuted}" Margin="0,8,0,0"/>
                    <TextBlock Text="PDF, DOCX, TXT, CSV · Max 10 MB"
                               Style="{StaticResource PotomacMonoLabel}"/>
                </StackPanel>
            </Border>
        </StackPanel>
    </ScrollViewer>
</Page>
```

---

## 14. Settings

### Settings View

```xml
<!-- Views/SettingsPage.xaml -->
<Page x:Class="AnalystApp.Views.SettingsPage">

    <ScrollViewer Padding="52,56" VerticalScrollBarVisibility="Auto">
        <StackPanel MaxWidth="1360">

            <!-- Hero -->
            <Border HorizontalAlignment="Left" CornerRadius="100"
                    Padding="14,5" Background="#14FEC00F"
                    BorderBrush="#33FEC00F" BorderThickness="1">
                <StackPanel Orientation="Horizontal" Spacing="10">
                    <Ellipse Width="5" Height="5" Fill="#FEC00F"/>
                    <TextBlock Text="Configuration · Active"
                               Style="{StaticResource PotomacMonoLabel}"
                               Foreground="#FEC00F" FontSize="9.5"/>
                </StackPanel>
            </Border>

            <TextBlock Text="Settings" Margin="0,24,0,6"
                       FontSize="52" FontWeight="ExtraBold" Foreground="#FEC00F"/>
            <TextBlock FontSize="24" Foreground="{ThemeResource PotomacTextMutedBrush}">
                Manage your account, appearance, and preferences.
            </TextBlock>

            <!-- Section Tabs -->
            <ScrollViewer Orientation="Horizontal" Margin="0,52,0,0"
                          HorizontalScrollBarVisibility="Hidden">
                <StackPanel Orientation="Horizontal" Spacing="10">
                    <Button Content="PROFILE" Tag="Profile"
                            Style="{StaticResource PotomacNavButton}"/>
                    <Button Content="API KEYS" Tag="ApiKeys"
                            Style="{StaticResource PotomacNavButton}"/>
                    <Button Content="APPEARANCE" Tag="Appearance"
                            Style="{StaticResource PotomacNavButton}"/>
                    <Button Content="NOTIFICATIONS" Tag="Notifications"
                            Style="{StaticResource PotomacNavButton}"/>
                    <Button Content="SECURITY" Tag="Security"
                            Style="{StaticResource PotomacNavButton}"/>
                    <Button Content="ABOUT" Tag="About"
                            Style="{StaticResource PotomacNavButton}"/>
                </StackPanel>
            </ScrollViewer>

            <!-- ═══ APPEARANCE SECTION ═══ -->
            <TextBlock Text="THEME MODE" Style="{StaticResource PotomacEyebrowLabel}"
                       Margin="0,0,0,14"/>

            <Grid Margin="0,0,0,32">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="*"/>
                </Grid.ColumnDefinitions>

                <Border Grid.Column="0" Style="{StaticResource PotomacCard}">
                    <StackPanel HorizontalAlignment="Center">
                        <FontIcon Glyph="&#xE706;" FontSize="24" Foreground="#FB923C"/>
                        <TextBlock Text="Light" FontSize="14" FontWeight="Bold"
                                   HorizontalAlignment="Center" Margin="0,14,0,4"/>
                        <TextBlock Text="Clean, bright interface"
                                   Style="{StaticResource PotomacMonoLabel}"/>
                    </StackPanel>
                </Border>

                <Border Grid.Column="1" Style="{StaticResource PotomacCard}" Margin="16,0"
                        BorderBrush="#A78BFA" BorderThickness="2">
                    <StackPanel HorizontalAlignment="Center">
                        <FontIcon Glyph="&#xE708;" FontSize="24" Foreground="#A78BFA"/>
                        <TextBlock Text="Dark" FontSize="14" FontWeight="Bold"
                                   HorizontalAlignment="Center" Margin="0,14,0,4"/>
                        <TextBlock Text="Easy on the eyes"
                                   Style="{StaticResource PotomacMonoLabel}"/>
                        <FontIcon Glyph="&#xE73E;" Foreground="#A78BFA"
                                  HorizontalAlignment="Center" Margin="0,10,0,0"/>
                    </StackPanel>
                </Border>

                <Border Grid.Column="2" Style="{StaticResource PotomacCard}">
                    <StackPanel HorizontalAlignment="Center">
                        <FontIcon Glyph="&#xE7F4;" FontSize="24" Foreground="#60A5FA"/>
                        <TextBlock Text="System" FontSize="14" FontWeight="Bold"
                                   HorizontalAlignment="Center" Margin="0,14,0,4"/>
                        <TextBlock Text="Match your OS"
                                   Style="{StaticResource PotomacMonoLabel}"/>
                    </StackPanel>
                </Border>
            </Grid>

            <!-- Accent Color -->
            <TextBlock Text="ACCENT COLOR" Style="{StaticResource PotomacEyebrowLabel}"/>
            <controls:AccentColorPicker Margin="0,14,0,0"/>

            <!-- Font Size -->
            <TextBlock Text="FONT SIZE" Style="{StaticResource PotomacEyebrowLabel}"
                       Margin="0,32,0,14"/>
            <StackPanel Orientation="Horizontal" Spacing="12">
                <Button Content="SMALL" Style="{StaticResource PotomacSecondaryButton}"/>
                <Button Content="MEDIUM" Style="{StaticResource PotomacPrimaryButton}"/>
                <Button Content="LARGE" Style="{StaticResource PotomacSecondaryButton}"/>
            </StackPanel>
        </StackPanel>
    </ScrollViewer>
</Page>
```

---

## 15. Animations & Transitions

### Page Transitions

```xml
<!-- In App.xaml or Frame setup: -->
<Frame x:Name="ContentFrame">
    <Frame.ContentTransitions>
        <TransitionCollection>
            <EntranceThemeTransition IsStaggeringEnabled="True"/>
        </TransitionCollection>
    </Frame.ContentTransitions>
</Frame>
```

### Button Hover Animation

```xml
<Style x:Key="PotomacHoverLiftButton" TargetType="Button">
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Grid x:Name="RootGrid" RenderTransformOrigin="0.5,0.5">
                    <Grid.RenderTransform>
                        <CompositeTransform x:Name="ButtonTransform" ScaleX="1" ScaleY="1" TranslateY="0"/>
                    </Grid.RenderTransform>

                    <Border x:Name="BackgroundBorder"
                            Background="{TemplateBinding Background}"
                            CornerRadius="{TemplateBinding CornerRadius}"
                            Padding="{TemplateBinding Padding}">
                        <ContentPresenter/>
                    </Border>

                    <VisualStateManager.VisualStateGroups>
                        <VisualStateGroup x:Name="CommonStates">
                            <VisualState x:Name="Normal"/>
                            <VisualState x:Name="PointerOver">
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="ButtonTransform"
                                                     Storyboard.TargetProperty="TranslateY"
                                                     To="-3" Duration="0:0:0.25">
                                        <DoubleAnimation.EasingFunction>
                                            <CubicEase EasingMode="EaseOut"/>
                                        </DoubleAnimation.EasingFunction>
                                    </DoubleAnimation>
                                    <DoubleAnimation Storyboard.TargetName="BackgroundBorder"
                                                     Storyboard.TargetProperty="Opacity"
                                                     To="0.95" Duration="0:0:0.2"/>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="Pressed">
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="ButtonTransform"
                                                     Storyboard.TargetProperty="TranslateY"
                                                     To="0" Duration="0:0:0.1"/>
                                </Storyboard>
                            </VisualState>
                        </VisualStateGroup>
                    </VisualStateManager.VisualStateGroups>
                </Grid>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### Pulse Animation

```xml
<!-- Status indicator pulse -->
<Ellipse Width="5" Height="5" Fill="#FEC00F">
    <Ellipse.Resources>
        <Storyboard x:Name="PulseAnimation" RepeatBehavior="Forever" AutoReverse="True">
            <DoubleAnimation Storyboard.TargetProperty="Opacity"
                             From="1" To="0.3" Duration="0:0:1.2"/>
            <DoubleAnimation Storyboard.TargetProperty="(RenderTransform).(ScaleTransform.ScaleX)"
                             From="1" To="0.6" Duration="0:0:1.2"/>
            <DoubleAnimation Storyboard.TargetProperty="(RenderTransform).(ScaleTransform.ScaleY)"
                             From="1" To="0.6" Duration="0:0:1.2"/>
        </Storyboard>
    </Ellipse.Resources>
    <Ellipse.RenderTransform>
        <ScaleTransform/>
    </Ellipse.RenderTransform>
</Ellipse>
```

### Loading Shimmer

```xml
<!-- Shimmer loading effect -->
<Border Background="{ThemeResource PotomacRaisedBrush}" CornerRadius="10"
        ClipToBounds="True">
    <Border Background="{ThemeResource PotomacAccentDimBrush}"
            CornerRadius="10" HorizontalAlignment="Left"
            Width="200">
        <Border.RenderTransform>
            <TranslateTransform x:Name="ShimmerTransform" X="-200"/>
        </Border.RenderTransform>
        <Border.Triggers>
            <EventTrigger RoutedEvent="Border.Loaded">
                <BeginStoryboard>
                    <Storyboard>
                        <DoubleAnimation Storyboard.TargetName="ShimmerTransform"
                                         Storyboard.TargetProperty="X"
                                         From="-200" To="400" Duration="0:0:1.5"
                                         RepeatBehavior="Forever"/>
                    </Storyboard>
                </BeginStoryboard>
            </EventTrigger>
        </Border.Triggers>
    </Border>
</Border>
```

---

## 16. Accessibility

### Keyboard Navigation

```xml
<!-- All buttons and controls support Tab navigation by default -->
<!-- Custom controls should set: -->
<Setter Property="IsTabStop" Value="True"/>
<Setter Property="TabIndex" Value="0"/>
```

### High Contrast

```xml
<!-- High contrast theme resources -->
<ResourceDictionary x:Key="HighContrast">
    <SolidColorBrush x:Key="PotomacBackgroundBrush" Color="{ThemeResource SystemColorWindowColor}"/>
    <SolidColorBrush x:Key="PotomacTextBrush" Color="{ThemeResource SystemColorWindowTextColor}"/>
    <SolidColorBrush x:Key="PotomacAccentBrush" Color="{ThemeResource SystemColorHighlightColor}"/>
</ResourceDictionary>
```

### Screen Reader Support

```csharp
// Set AutomationProperties on all interactive elements
AutomationProperties.SetName(button, "Generate AFL code");
AutomationProperties.SetHelpText(button, "Generates AmiBroker AFL code from your strategy description");
```

---

## 17. Complete App Structure

```
AnalystApp/
├── App.xaml
├── App.xaml.cs
├── MainWindow.xaml
├── MainWindow.xaml.cs
│
├── Assets/
│   ├── Fonts/
│   │   ├── Syne-Variable.ttf
│   │   ├── DM_Mono/
│   │   └── InstrumentSans/
│   ├── potomac-icon.png
│   └── potomac-logo.png
│
├── Controls/
│   ├── AccentColorPicker.xaml/.cs
│   ├── PotomacPage.xaml/.cs
│   ├── PotomacSidebar.xaml/.cs
│   ├── SectionHeader.xaml/.cs
│   └── Sparkline.xaml/.cs
│
├── Models/
│   ├── ApiModels.cs
│   └── DomainModels.cs
│
├── Services/
│   ├── ApiConfig.cs
│   ├── ApiService.cs
│   ├── ApiService.Auth.cs
│   ├── ApiService.Chat.cs
│   ├── ApiService.Afl.cs
│   ├── SecureStorage.cs
│   ├── ThemeService.cs
│   └── NavigationService.cs
│
├── Styles/
│   ├── PotomacStyles.xaml      ← Button, TextBox, Toggle styles
│   └── PotomacControls.xaml    ← Reusable control templates
│
├── Themes/
│   ├── PotomacTheme.xaml       ← Dark theme tokens
│   ├── DarkTheme.xaml
│   └── LightTheme.xaml
│
├── ViewModels/
│   ├── BaseViewModel.cs
│   ├── LoginViewModel.cs
│   ├── DashboardViewModel.cs
│   ├── ChatViewModel.cs
│   ├── AflViewModel.cs
│   ├── KnowledgeBaseViewModel.cs
│   └── SettingsViewModel.cs
│
└── Views/
    ├── LoginPage.xaml/.cs
    ├── RegisterPage.xaml/.cs
    ├── DashboardPage.xaml/.cs
    ├── ChatPage.xaml/.cs
    ├── AflGeneratorPage.xaml/.cs
    ├── KnowledgeBasePage.xaml/.cs
    └── SettingsPage.xaml/.cs
```

---

## Quick Reference: Web → WinUI 3 Mapping

| Web (CSS/Tailwind) | WinUI 3 (XAML) |
|---|---|
| `<div>` | `<Grid>`, `<StackPanel>`, `<Border>` |
| `background: var(--bg-card)` | `Background="{ThemeResource PotomacCardBrush}"` |
| `border: 1px solid` | `BorderBrush="{ThemeResource PotomacBorderBrush}" BorderThickness="1"` |
| `border-radius: 20px` | `CornerRadius="20"` |
| `box-shadow` | `<DropShadowEffect>` or `ThemeShadow` |
| `display: flex` | `<StackPanel Orientation="Horizontal">` or `<Grid>` |
| `grid-template-columns` | `<Grid.ColumnDefinitions>` |
| `position: absolute` | `<Canvas>` or `HorizontalAlignment/VerticalAlignment` |
| `overflow: hidden` | `ClipToBounds="True"` |
| `transition` | `<Storyboard>` in `<VisualState>` |
| `hover` | `<VisualState x:Name="PointerOver">` |
| `@media (max-width: 768px)` | `VisualStateGroup` with `AdaptiveTrigger` |
| `color-scheme: dark` | `RequestedTheme="Dark"` or theme resource swap |
| `font-family: Syne` | `FontFamily="{StaticResource SyneFont}"` |
| `text-transform: uppercase` | `<Style>` with `CharacterSpacing` (Caps not native) |
| `letter-spacing` | `CharacterSpacing` (in hundredths of em) |
| `opacity` | `Opacity="0.5"` |
| `linear-gradient` | `<LinearGradientBrush>` |
| `radial-gradient` | `<RadialGradientBrush>` |
| CSS variables (`var(--accent)`) | `ThemeResource` / `StaticResource` |
| `Tailwind responsive grid` | `AdaptiveTrigger` in `VisualStateGroup` |
| `react-hook-form` | `x:Bind` with MVVM `[ObservableProperty]` |
| `useContext` | `DependencyInjection` + `App.GetService<T>()` |
| `useState` | `[ObservableProperty]` from CommunityToolkit.Mvvm |

---

**Last Updated:** March 2026
**Design System Version:** RC 2.0
**Framework:** WinUI 3 (Windows App SDK) / .NET 8+ / C#
**Platforms:** Windows 11 22H2+